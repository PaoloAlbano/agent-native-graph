"use strict";

// Shared by the browser and lightweight Node contract tests.
const ANAResultsUI = {
  outcome(record) {
    if (!record.ok) return "Execution failed";
    return record.matches_answer_json ? "Exact benchmark match" : "Executed, but answer mismatch";
  },
  focusQuestion(panel) {
    panel.scrollIntoView({ block: "start" });
    const heading = panel.querySelector("h3");
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
    }
  },
  createTrajectory(document, record, prefix = "ana") {
    const node = (tag, text, className) => {
      const element = document.createElement(tag);
      if (text !== undefined) element.textContent = text;
      if (className) element.className = className;
      return element;
    };
    const container = node("section", undefined, "ana-trajectory");
    const steps = record.transcript || [];
    container.append(node("h3", `ANA execution flow · ${steps.length} recorded steps`));
    if (record.error || record.failure_class) {
      container.append(node("p", `Recorded failure: ${record.failure_class || "unclassified"}`, "outcome failed"));
      if (record.error) container.append(node("pre", record.error, "execution-error"));
    }
    if (!steps.length) {
      const noTools = record.tool_call_count === 0;
      container.append(node("p", noTools
        ? "No tool was executed. There is no tool-call trajectory to display."
        : "No tool steps were saved in this archive; the trajectory cannot be reconstructed."));
      if (noTools && record.failure_class === "json_decode") container.append(node("p",
        "The runner stopped while parsing an LLM response, before executing a tool. The failed response text and tool arguments were not archived; they cannot be reconstructed."));
    }
    container.append(node("p", "Input handles open the recorded response that created them. These are archived previews, not live server state. Model reasoning is not reconstructed.", "small-text"));
    const handles = new Map();
    const references = (value) => {
      if (typeof value === "string") return handles.has(value) ? [value] : [];
      if (!value || typeof value !== "object") return [];
      return [...new Set(Object.values(value).flatMap(references))];
    };
    const sequence = node("ol", undefined, "recorded-sequence");
    steps.forEach((step, index) => {
      const item = node("li");
      const action = step.action || {};
      const result = step.result;
      item.append(node("h4", action.tool || "Recorded event"));
      const refs = references(action.args);
      if (refs.length) {
        const flow = node("div", "Input handles: ", "handle-flow");
        for (const handle of refs) {
          const button = node("button", handle, "handle-link");
          const target = handles.get(handle);
          button.addEventListener("click", () => {
            target.open = true;
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.querySelector("summary").focus();
          });
          flow.append(button);
        }
        item.append(flow);
      }
      if (result?.error) item.append(node("p", `Tool error: ${result.error}`, "outcome failed"));
      else if (result && typeof result === "object") {
        const info = [];
        if (result.handle) info.push(`Created ${result.handle}`);
        if (typeof result.matched_count === "number") info.push(`${result.matched_count} matching rows`);
        if (typeof result.returned_count === "number") info.push(`${result.returned_count} returned rows`);
        if (result.columns?.length) info.push(`Columns: ${result.columns.join(", ")}`);
        if (result.truncated === true) info.push("Truncation flag recorded; inspect response metadata");
        if (info.length) item.append(node("p", info.join(" · "), "step-summary"));
      }
      item.append(ANAResultsUI.createDisclosure(document, "Arguments", action.args ?? {}));
      const response = ANAResultsUI.createDisclosure(document, "Recorded response", result ?? step);
      if (result?.handle) {
        response.id = `${prefix}-step-${index}`;
        response.querySelector("summary").textContent = `Output ${result.handle} · recorded response`;
        handles.set(result.handle, response);
      }
      item.append(response);
      const extra = Object.fromEntries(Object.entries(step).filter(([key]) => !["action", "result"].includes(key)));
      if (Object.keys(extra).length) item.append(ANAResultsUI.createDisclosure(document, "Other recorded event fields", extra));
      sequence.append(item);
    });
    if (steps.length) container.append(sequence);
    if (record.request_accounting) container.append(ANAResultsUI.createDisclosure(document, "Recorded request accounting", record.request_accounting));
    return container;
  },
  matchesQid(qid, query) {
    return qid.toLowerCase().includes(query.trim().toLowerCase());
  },
  createDisclosure(document, title, value) {
    const element = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = title;
    element.append(summary);
    element.addEventListener("toggle", () => {
      if (!element.open) {
        while (element.children.length > 1) element.lastChild.remove();
        return;
      }
      if (element.children.length > 1) return;
      const text = JSON.stringify(value, null, 2) ?? "null";
      const limit = 20000;
      if (text.length > limit) {
        const note = document.createElement("p");
        note.className = "small-text";
        note.textContent = `Preview: first ${limit.toLocaleString()} characters. Download the question record below for the complete JSON.`;
        element.append(note);
      }
      const pre = document.createElement("pre");
      pre.textContent = text.slice(0, limit);
      element.append(pre);
    });
    return element;
  },
};
if (typeof module !== "undefined") module.exports = ANAResultsUI;
