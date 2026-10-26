"use strict";

// Shared by the browser and lightweight Node contract tests.
const ANAResultsUI = {
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
