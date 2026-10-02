(() => {
  const form = document.querySelector("[data-report-filters]");
  if (!form) return;
  const rows = [...document.querySelectorAll("[data-filter-row]")];
  const count = form.querySelector("[data-filter-count]");
  const headers = [...document.querySelectorAll("[data-group-header]")];
  const apply = () => {
    const search = form.elements.namedItem("search").value.trim().toLowerCase();
    const kind = form.elements.namedItem("kind").value;
    const component = form.elements.namedItem("component").value;
    const status = form.elements.namedItem("status").value;
    let visible = 0;
    for (const row of rows) {
      const failWithUnknown = row.dataset.status === "FAIL"
        && Number(row.dataset.undecided) > 0;
      const statusMatches = !status || row.dataset.status === status
        || ((status === "FAIL+UNKNOWN" || status === "UNKNOWN") && failWithUnknown);
      const matches = (!search || row.dataset.search.toLowerCase().includes(search))
        && (!kind || row.dataset.kind === kind)
        && (!component || row.dataset.component.split(" ").includes(component))
        && statusMatches;
      row.hidden = !matches;
      visible += Number(matches);
    }
    for (const header of headers) {
      let child = header.nextElementSibling;
      let hasVisibleChild = false;
      while (child && !child.matches("[data-group-header]")) {
        hasVisibleChild ||= !child.hidden;
        child = child.nextElementSibling;
      }
      header.hidden = !hasVisibleChild;
    }
    count.textContent = `${visible} of ${rows.length} rows`;
  };
  form.addEventListener("input", apply);
  form.addEventListener("change", apply);
  form.addEventListener("reset", () => requestAnimationFrame(apply));
  form.hidden = false;
  apply();
})();
(() => {
  for (const button of document.querySelectorAll("[data-copy-review]")) {
    button.hidden = false;
    button.addEventListener("click", async () => {
      const box = button.parentElement.querySelector("textarea");
      const status = button.parentElement.querySelector("output");
      box.focus();
      box.select();
      try {
        await navigator.clipboard.writeText(box.value);
        status.textContent = "Copied.";
      } catch {
        status.textContent = "Selected. Press Ctrl+C or Cmd+C to copy.";
      }
    });
  }
  const reveal = () => {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    const target = document.getElementById(id);
    if (!target || !target.hasAttribute("data-finding-id")) return;
    const filters = document.querySelector("[data-report-filters]");
    if (filters) filters.reset();
    for (let parent = target.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === "DETAILS") parent.open = true;
    }
    requestAnimationFrame(() => {
      target.scrollIntoView();
      target.focus();
    });
  };
  window.addEventListener("hashchange", reveal);
  reveal();
})();
