"use strict";

const family = document.querySelector("#tool-group");
const statusFilter = document.querySelector("#tool-status");
const availability = document.querySelector("#tool-availability");
const controls = [family, statusFilter, availability];
const cards = [...document.querySelectorAll(".tool-card")];
const groups = [...document.querySelectorAll(".tool-group")];
const count = document.querySelector("#tool-count");
const reset = document.querySelector("#reset-filters");

function filterTools() {
  let visibleCount = 0;
  let visibleGroups = 0;
  groups.forEach((group) => {
    let members = 0;
    group.querySelectorAll(".tool-card").forEach((card) => {
      const visible = (family.value === "all" || family.value === group.dataset.group)
        && (statusFilter.value === "all" || statusFilter.value === card.dataset.status)
        && (availability.value === "all" || availability.value === card.dataset.availability);
      card.hidden = !visible;
      members += Number(visible);
    });
    group.hidden = members === 0;
    group.querySelector(".group-count").textContent = String(members).padStart(2, "0");
    visibleCount += members;
    visibleGroups += Number(members > 0);
  });
  count.textContent = `${visibleCount} of ${cards.length} tools · ${visibleGroups} ${visibleGroups === 1 ? "family" : "families"}`;
  document.querySelector("#no-tools").hidden = visibleCount > 0;
  reset.hidden = controls.every((control) => control.value === "all");
}

function clearFilters() {
  controls.forEach((control) => { control.value = "all"; });
  filterTools();
}

function revealLinkedDetail() {
  let id;
  try { id = decodeURIComponent(window.location.hash.slice(1)); } catch { return; }
  const target = document.getElementById(id);
  if (!target || !target.matches(".tool-card, .handle-snapshot")) return;
  if (target.matches(".tool-card")) clearFilters();
  target.open = true;
  requestAnimationFrame(() => target.scrollIntoView({ block: "start" }));
}

controls.forEach((control) => {
  control.disabled = false;
  control.addEventListener("change", filterTools);
});
document.querySelector(".catalog-controls").addEventListener("submit", (event) => event.preventDefault());
reset.addEventListener("click", () => { clearFilters(); family.focus(); });
window.addEventListener("hashchange", revealLinkedDetail);
document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href^="#tool-"], a[href^="#example-handle-"]');
  if (link && link.hash === window.location.hash) revealLinkedDetail();
});
filterTools();
revealLinkedDetail();
