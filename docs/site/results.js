"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { runs: [], qid: null, generation: 0, selection: 0 };
  const detailPanel = $("question-detail");
  const cache = new Map();
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const disclosure = (title, value) => ANAResultsUI.createDisclosure(document, title, value);
  const link = (text, href) => {
    const element = node("a", text);
    element.href = href;
    return element;
  };
  const run = (side) => state.runs.find((r) => r.config.run_id === $(`run-${side}`).value);
  const label = (r) => `${r.config.model} · Temperature ${r.config.temperature} · Reasoning ${r.config.reasoning} · ${r.label}`;
  const outcome = (q) => q.matches_answer_json ? "Correct" : q.ok ? "Answer mismatch" : "Execution not OK";

  async function getJSON(path) {
    if (cache.has(path)) return cache.get(path);
    const response = await fetch(path);
    if (!response.ok) throw new Error(`Cannot load ${path} (HTTP ${response.status})`);
    const value = await response.json();
    // Keep navigation bounded even when readers browse every trajectory.
    if (cache.size >= 2) cache.delete(cache.keys().next().value);
    cache.set(path, value);
    return value;
  }

  function saveLocation() {
    const params = new URLSearchParams();
    if ($("run-b").value) params.set("b", $("run-b").value);
    if (state.qid) params.set("q", state.qid);
    history.replaceState(null, "", `#${params}`);
  }

  function refreshFailureOptions() {
    const previous = $("failure").value;
    $("failure").replaceChildren(new Option("All classes", "all"));
    const classes = [...new Set(run("a").questions.map((q) => q.failure_class).filter(Boolean))].sort();
    for (const name of classes) $("failure").add(new Option(name, name));
    if (classes.includes(previous)) $("failure").value = previous;
  }

  function filteredQuestions() {
    const query = $("question-search").value.trim().toLowerCase();
    const comparison = new Map((run("b")?.questions || []).map((q) => [q.qid, q]));
    return run("a").questions.filter((q) => {
      if (!ANAResultsUI.matchesQid(q.qid, query)) return false;
      if ($("failure").value !== "all" && q.failure_class !== $("failure").value) return false;
      switch ($("outcome").value) {
        case "correct": return q.matches_answer_json;
        case "mismatch": return q.ok && !q.matches_answer_json;
        case "error": return !q.ok;
        case "different": return comparison.has(q.qid) && q.matches_answer_json !== comparison.get(q.qid).matches_answer_json;
        default: return true;
      }
    });
  }

  function renderQuestions() {
    const questions = filteredQuestions();
    $("load-status").textContent = `${questions.length} of 347 questions match. Outcomes refer to run A.`;
    if ($("outcome").value === "different" && !run("b")) $("load-status").textContent = "Select a comparison run to see differences.";
    detailPanel.remove();
    detailPanel.hidden = true;
    $("question-list").replaceChildren();
    for (const q of questions) {
      const row = node("tr", undefined, "question-row");
      const question = node("td");
      question.append(node("p", q.nl_question), node("small", q.qid));
      const status = node("td");
      status.append(node("span", outcome(q), q.matches_answer_json ? "outcome correct" : "outcome failed"));
      const control = node("td");
      const button = node("button", q.qid === state.qid ? "Close" : "Inspect", "inspect-question");
      button.setAttribute("aria-expanded", String(q.qid === state.qid));
      button.setAttribute("aria-controls", "question-detail");
      button.setAttribute("aria-label", `${q.qid === state.qid ? "Close" : "Inspect"} ${q.qid}`);
      button.addEventListener("click", () => {
        state.qid = state.qid === q.qid ? null : q.qid;
        renderQuestions();
        showQuestion();
      });
      control.append(button);
      row.append(question, status, node("td", String(q.llm_call_count ?? "—")), node("td", String(q.tool_call_count ?? "—")), control);
      $("question-list").append(row);
      if (q.qid === state.qid) {
        const expanded = node("tr", undefined, "question-expanded");
        const cell = node("td");
        cell.colSpan = 5;
        detailPanel.hidden = false;
        cell.append(detailPanel);
        expanded.append(cell);
        $("question-list").append(expanded);
      }
    }
    if (detailPanel.hidden) { detailPanel.replaceChildren(); document.querySelector(".explorer").append(detailPanel); }
  }

  const renderTrajectory = (record, pane) => ANAResultsUI.createTrajectory(document, record, pane);

  function renderRun(record, selectedRun, side, path) {
    const pane = node("article", undefined, "run-detail");
    pane.append(node("h3", `Run ${side.toUpperCase()}`), node("p", label(selectedRun), "run-label"));
    pane.append(node("p", outcome(record), record.matches_answer_json ? "outcome correct" : "outcome failed"));
    pane.append(node("p", `${record.llm_call_count ?? "Not recorded"} LLM calls · ${record.tool_call_count ?? "Not recorded"} tool calls · ${record.tool_error_count ?? "Not recorded"} tool errors · ${typeof record.elapsed_s === "number" ? record.elapsed_s.toFixed(2) + " s" : "Time not recorded"}`));
    if (record.error || record.failure_class) pane.append(disclosure("Failure / error", { failure_class: record.failure_class, error: record.error }));
    const answer = disclosure("Returned answer", record.rows ?? null);
    answer.open = true;
    pane.append(answer, renderTrajectory(record, side));
    for (const key of ["reasoning_content", "reasoning", "messages", "content", "response"]) {
      if (record[key] !== undefined) pane.append(disclosure(`Recorded ${key}`, record[key]));
    }
    if (!record.reasoning_content && !record.reasoning && !record.messages && !record.response) pane.append(node("p", "Raw model messages and reasoning text were not archived for this question. Tool calls and call metrics are available below.", "small-text"));
    pane.append(disclosure("LLM call metrics", record.llm_call_metrics ?? null), disclosure("Run configuration & provenance", selectedRun.config));
    const download = link("Download question record (JSON)", path);
    download.download = "";
    pane.append(download, node("span", " · "), link("Source archive", selectedRun.source));
    return pane;
  }

  async function showQuestion() {
    const generation = ++state.generation;
    saveLocation();
    if (!state.qid) return;
    $("question-detail").replaceChildren(node("p", "Loading the recorded trajectory…"));
    try {
      const selected = [run("a"), run("b")].filter(Boolean);
      const details = await Promise.all(selected.map(async (r) => {
        const question = r.questions.find((q) => q.qid === state.qid);
        if (!question) throw new Error("Question is missing from the selected run.");
        return { record: await getJSON(question.detail), path: question.detail };
      }));
      if (generation !== state.generation) return;
      const record = details[0].record;
      const heading = node("h3", record.nl_question);
      const qid = node("p", record.qid, "question-qid");
      const gold = disclosure("Golden Cypher query", record.gold_cypher);
      const expected = disclosure("Expected benchmark answer", record.expected);
      const panes = node("div", undefined, selected.length > 1 ? "run-panes comparing" : "run-panes");
      details.forEach((detail, i) => panes.append(renderRun(detail.record, selected[i], i === 0 ? "a" : "b", detail.path)));
      $("question-detail").replaceChildren(heading, qid, gold, expected, panes);
      ANAResultsUI.focusQuestion(detailPanel);
    } catch (error) {
      if (generation !== state.generation) return;
      const retry = node("button", "Retry loading this question");
      retry.addEventListener("click", showQuestion);
      $("question-detail").replaceChildren(node("p", error.message), retry);
    }
  }

  async function init() {
    try {
      const data = await getJSON("data/results/index.json");
      const active = await getJSON(document.body.dataset.runIndex);
      state.runs = data.runs;
      Object.assign(state.runs.find((r) => r.config.run_id === active.config.run_id), active);
      $("run-b").add(new Option("No comparison", ""));
      $("run-a").add(new Option(label(active), active.config.run_id));
      for (const r of state.runs) $("run-b").add(new Option(label(r), r.config.run_id));
      const params = new URLSearchParams(location.hash.slice(1));
      if (state.runs.some((r) => r.config.run_id === params.get("b"))) $("run-b").value = params.get("b");
      if (run("a").questions.some((q) => q.qid === params.get("q"))) state.qid = params.get("q");
      async function refreshSelection() {
        const selection = ++state.selection;
        state.generation++;
        const comparison = run("b");
        $("load-status").textContent = "Loading selected run…";
        try {
          if (comparison && !comparison.questions) {
            const payload = await getJSON(comparison.question_index);
            if (selection !== state.selection) return;
            comparison.questions = payload.questions;
          }
          for (const r of state.runs) if (r !== run("a") && r !== comparison) delete r.questions;
          document.querySelectorAll(".explorer-controls select, .explorer-controls input").forEach((element) => { element.disabled = element.id === "run-a"; });
          refreshFailureOptions();
          renderQuestions();
          showQuestion();
        } catch (error) {
          if (selection !== state.selection) return;
          $("load-status").textContent = `Could not load comparison: ${error.message}. Select the run again to retry.`;
          $("run-b").disabled = false;
        }
      }
      $("run-b").addEventListener("change", refreshSelection);
      window.addEventListener("hashchange", () => {
        const next = new URLSearchParams(location.hash.slice(1));
        $("run-b").value = state.runs.some((r) => r.config.run_id === next.get("b")) ? next.get("b") : "";
        state.qid = run("a").questions.some((q) => q.qid === next.get("q")) ? next.get("q") : null;
        $("question-search").value = "";
        $("outcome").value = "all";
        $("failure").value = "all";
        refreshSelection();
      });
      for (const id of ["question-search", "outcome", "failure"]) $(id).addEventListener("input", () => { state.qid = null; state.generation++; saveLocation(); renderQuestions(); });
      await refreshSelection();
    } catch (error) {
      $("load-status").textContent = `${error.message}. Reload to retry. Serve the built site with make docs-serve; opening file:// URLs does not support fetching data.`;
    }
  }
  init();
})();
