(() => {
  const form = document.querySelector("[data-report-filters]");
  if (!form) return;
  const rows = [...document.querySelectorAll("[data-filter-row]")];
  const count = form.querySelector("[data-filter-count]");
  const apply = () => {
    const search = form.elements.namedItem("search").value.trim().toLowerCase();
    const kind = form.elements.namedItem("kind").value;
    const component = form.elements.namedItem("component").value;
    const status = form.elements.namedItem("status").value;
    let visible = 0;
    for (const row of rows) {
      const matches = (!search || row.dataset.search.toLowerCase().includes(search))
        && (!kind || row.dataset.kind === kind)
        && (!component || row.dataset.component.split(" ").includes(component))
        && (!status || row.dataset.status === status);
      row.hidden = !matches;
      visible += Number(matches);
    }
    count.textContent = `${visible} of ${rows.length} rows`;
  };
  form.addEventListener("input", apply);
  form.addEventListener("change", apply);
  form.addEventListener("reset", () => requestAnimationFrame(apply));
})();
