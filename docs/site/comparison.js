"use strict";
(() => {
  const root = document.getElementById("comparison-detail");
  const node = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const detail = (title, value) => ANAResultsUI.createDisclosure(document, title, value);
  const link = (title, path) => { const e = node("a", title); e.href = path; return e; };
  async function read(path) {
    const response = await fetch(path);
    if (!response.ok) throw new Error(`Could not load evidence (${response.status})`);
    return response.json();
  }
  function download(path) {
    const e = link("Download complete question evidence (JSON)", path); e.download = ""; return e;
  }
  async function show() {
    root.replaceChildren(node("p", "Loading this question’s evidence…"));
    try {
      const config = await read(document.body.dataset.comparison);
      const ana = await read(config.ana.detail);
      const header = node("div");
      header.append(detail("Golden Cypher", ana.gold_cypher), detail("Expected benchmark rows", ana.expected));
      if (config.gold_reproduced === false) header.prepend(node("p", "The golden query did not reproduce the expected rows. This question remains included in the 100-case scores; the discrepancy is pending investigation."));
      const pane = node("article"); pane.className = "run-detail";
      pane.append(node("h2", "ANA · exact answer matching"), node("p", ana.matches_answer_json ? "Match" : "No match"), node("p", `${ana.llm_call_count} LLM calls · ${ana.tool_call_count} tool calls (runner counters)`), detail("Returned rows", ana.rows), detail("Configuration", config.ana.config));
      (ana.transcript || []).forEach((step, i) => {
        pane.append(node("h3", `${i + 1}. ${step.action?.tool || "Recorded event"}`), detail("Arguments", step.action?.args), detail("Tool response", step.result));
      });
      pane.append(link("Open full ANA run analysis", config.ana.page), node("p", "Raw model request/response text is unavailable in these ANA archives; it is not reconstructed."), download(config.ana.detail));
      root.replaceChildren(header, pane);
      for (const [mode, reference] of Object.entries(config.external)) {
        const data = await read(reference.detail);
        const section = node("article"); section.className = "run-detail";
        const logs = data.logs["calls.jsonl"] || [];
        if (data.execution) {
          section.append(node("h2", mode === "single" ? "Direct Cypher · re-executed query" : "Multi-agent · re-executed query"), node("p", data.execution.matches_answer_json ? "Exact benchmark match" : "No exact benchmark match"), detail("Re-executed returned rows", data.execution.rows), detail("Re-execution details and errors", data.execution));
        }
        section.append(node("h2", mode === "single" ? "Direct Cypher · source LLM judge" : "Multi-agent GraphRAG · source LLM judge"), node("p", `${data.trace.correct ? "Correct" : "Incorrect"} according to the source judge (${reference.config.judge_mode}). This is not ANA exact matching.`), node("p", `${logs.length} logged pipeline calls (not an inferred total)`), detail("Generated Cypher", data.trace.generated_cypher), detail("Textual answer", data.trace.answer), detail("Source verdict and complete trace", data.trace), detail("Configuration", reference.config));
        logs.forEach((call, i) => {
          section.append(node("h3", `${i + 1}. ${call.agent || "LLM call"}`), detail("System prompt", call.system_prompt), detail("User prompt", call.user_prompt), detail("Response", call.response), detail("Complete recorded call", call));
        });
        for (const name of ["judge_calls.jsonl", "judge_fixed_calls.jsonl"]) if (data.logs[name]) section.append(detail(`Separate evaluation calls · ${name}`, data.logs[name]));
        section.append(download(reference.detail), node("span", " · "), link("Pinned source trace", data.source));
        root.append(section);
      }
      root.removeAttribute("role");
    } catch (error) {
      const retry = node("button", "Retry"); retry.addEventListener("click", show);
      root.append(node("p", error.message), retry);
    }
  }
  show();
})();
