  // The Health check drawer: findings, balance, question candidates and the module matrix.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  function atlasBalanceLine(title, balance) {
    return `${title}: ${balance?.declared ?? "UNKNOWN"} declared · ${balance?.used ?? "UNKNOWN"} used · ${balance?.allowed_unused ?? "UNKNOWN"} allowed but unused · ${balance?.undeclared ?? "UNKNOWN"} undeclared`;
  }
  function atlasDeviationHref(deviation) {
    const query = new URLSearchParams(location.search);
    query.delete("scope");
    if (deviation.level_id) query.set("component", deviation.level_id);
    else query.delete("component");
    query.set("view", "diff");
    query.set("selected", deviation.source_id);
    query.delete("content");
    return `${location.pathname}?${query}`;
  }
  function atlasBalanceMarkup(level) {
    if (S.view !== "diff") return "";
    const own = new Set(level.deviation_ids || []);
    const deviations = (ATLAS.deviations || []).filter((item) => own.has(item.id));
    return `<section class="atlas-balance"><p>${esc(atlasBalanceLine("This level", level.balance))}</p>
      <p>${esc(atlasBalanceLine("Whole system", ATLAS.balance))}</p>
      ${deviations.length ? `<ul class="plain">${deviations.map((item) => {
        const source = REPORT_SCENE.atlasComponent(item.source_id)?.label || item.source_id;
        const target = REPORT_SCENE.atlasComponent(item.target_id)?.label || item.target_id;
        const kind = item.kind === "allowed_unused" ? "Allowed but unused" : "Undeclared";
        return `<li><a href="${esc(atlasDeviationHref(item))}">${esc(kind)} · ${esc(source)} → ${esc(target)}</a></li>`;
      }).join("")}</ul>` : ""}</section>`;
  }
  function atlasInsideDeviations(componentId) {
    const ids = new Set();
    for (const level of ATLAS.levels) {
      if (level.parent_id === componentId || REPORT_SCENE.componentRoute(level.parent_id).some((item) => item.id === componentId)) {
        (level.deviation_ids || []).forEach((id) => ids.add(id));
      }
    }
    return (ATLAS.deviations || []).filter((row) => ids.has(row.id));
  }
  function atlasComponentFindingCount(componentId) {
    const level = ATLAS.levels.find((item) => item.parent_id === componentId);
    return level ? atlasFindings(level).length : 0;
  }
  function atlasGlobalSymbolsComplete() {
    if (typeof ATLAS.symbols_complete === "boolean") return ATLAS.symbols_complete;
    return ATLAS.modules.length > 0 && ATLAS.modules.every((module) =>
      module.symbol_coverage.length > 0 && module.symbol_coverage.every((item) => item.status === "complete"));
  }
  function atlasFindingsMarkup(level, modules) {
    const findings = atlasFindings(level), groups = new Map();
    findings.forEach((finding) => {
      for (const rule of finding.rule_ids.length ? finding.rule_ids : [""]) {
        const key = `${rule}\0${finding.kind}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(finding);
      }
    });
    return `<details class="atlas-findings" open><summary>Findings · ${findings.length}</summary>
      ${[...groups].map(([key, entries]) => {
      const [rule, kind] = key.split("\0");
      const sharedRemedy = entries.length > 1 && entries.every((finding) =>
        finding.remedy && finding.remedy === entries[0].remedy) ? entries[0].remedy : null;
      return `<details id="atlas-rule-${esc(rule)}" class="atlas-finding-group"><summary>${esc(rule)} · ${esc(kind)} · ${REPORT_SCENE.countLabel(entries.length, "finding")}</summary>${sharedRemedy ? `<p class="atlas-shared-remedy">${esc(sharedRemedy)}</p>` : ""}<ul class="plain">${entries.map((finding) => {
      const recorded = ATLAS.modules.find((item) => item.path === finding.path);
      const assignment = level.modules.find((item) => item.id === recorded?.id);
      const module = modules.find((item) => item.path === finding.path)
        || (recorded ? { ...recorded, ...assignment } : null);
      const source = finding.path ? `${finding.path}${finding.line ? `:${finding.line}` : ""}` : "Source not recorded";
        const href = module ? atlasModuleHref(module.id) : null;
        const remedy = finding.remedy && finding.remedy !== sharedRemedy
          ? `<p class="atlas-finding-remedy">${esc(finding.remedy)}</p>` : "";
        const nested = finding.nested_annotation
          ? `<p class="atlas-nested-annotation">Nested type: <code>${esc(finding.nested_annotation)}</code></p>` : "";
        return `<li id="atlas-finding-${esc(finding.id)}-${esc(encodeURIComponent(rule))}"><strong>${esc(finding.title)}</strong>${nested}<p>${href ? `<a href="${esc(href)}" data-atlas-module-route="${esc(module.id)}">${esc(source)}</a>` : `<code>${esc(source)}</code>`}</p>${remedy}</li>`;
      }).join("")}</ul></details>`;
      }).join("") || "<p>No recorded findings at this level.</p>"}</details>`;
  }
  function openAtlasFindingHash(requestedId = null) {
    let id = requestedId;
    if (id === null) {
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { pendingAtlasFindingHash = null; return; }
    }
    if (openBoundaryPermissionHash(id)) return;
    if (!id.startsWith("atlas-rule-") && !id.startsWith("atlas-finding-") && !id.startsWith("atlas-assessment-")) {
      pendingAtlasFindingHash = null;
      return;
    }
    const target = document.getElementById(id);
    if (!target) { pendingAtlasFindingHash = id; return; }
    pendingAtlasFindingHash = null;
    if (inspector.contains(target)) setTargetDetails(true);
    if (root.querySelector(".flow-explore")?.contains(target))
      root.dispatchEvent(new CustomEvent("archkeel:findings"));
    for (let ancestor = target; ancestor; ancestor = ancestor.parentElement) {
      if (ancestor instanceof HTMLDetailsElement) ancestor.open = true;
    }
    requestAnimationFrame(() => target.scrollIntoView());
  }
  window.addEventListener("hashchange", () => openAtlasFindingHash());
  root.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, location.href);
    if (url.pathname === location.pathname && url.search === location.search && url.hash === location.hash)
      openAtlasFindingHash();
  });

  function atlasQuestion(hint) {
    const subject = hint.kind === "hub" ? ["importing module", "importing modules"]
      : hint.kind === "heavy" ? ["symbol", "symbols"]
        : hint.kind === "no_owner" ? ["authenticated owner", "authenticated owners"]
          : ["import site", "import sites"];
    return `Repository: ${ATLAS.repository}\nCommit: ${ATLAS.source.git_head}\nSource digest: ${ATLAS.source.source_digest}\nModules: ${hint.module_ids.map((id) => REPORT_SCENE.atlasModuleById(id).name).join(", ")}\nObserved count: ${REPORT_SCENE.countLabel(hint.count, ...subject)}\nEvidence IDs: ${atlasReferences(hint, "evidence_ids").join(", ")}\nRelationship IDs: ${atlasReferences(hint, "relationship_ids").join(", ")}\nQuestion: ${hint.question}\nProvisional hint, not a verdict.`;
  }

  async function copyAtlasQuestion(hint, button) {
    const text = atlasQuestion(hint);
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch {
      const area = document.createElement("textarea");
      area.readOnly = true; area.value = text;
      area.setAttribute("aria-label", "Question and recorded evidence");
      button.parentElement.appendChild(area); area.focus(); area.select();
    }
  }

  function atlasModuleList(level) {
    const modules = REPORT_SCENE.atlasModules(level, S.view);
    return `<section class="atlas-module-list"><h3>${S.view === "target" ? "Declared" : "Observed"} ${REPORT_SCENE.countLabel(modules.length, "module")}</h3><ul class="plain">
      ${modules.map((module) => `<li>${atlasModuleLink(module, module.path?.split("/").at(-1) || module.name)}
        · ${S.view === "target" ? REPORT_SCENE.countLabel(module.declarations, "direct declared definition") : REPORT_SCENE.countLabel(module.symbols, "observed symbol")}
        <p><code>${esc(module.path || module.name)}</code>${module.path ? "" : " · File path not declared"}</p></li>`).join("")}</ul></section>`;
  }

  let atlasExploreModules = [];

  function setAtlasExploreOpen(open) {
    S.explore = open;
    if (open) atlasMatrix(atlasLevel(), atlasExploreModules);
  }

  function atlasExplore(level) {
    const explore = root.querySelector(".flow-explore");
    if (S.view === "target") {
      explore.innerHTML = `${atlasFindingsMarkup(level, REPORT_SCENE.atlasModules(level, S.view))}<h3>Explore</h3><p>Target shows declarations only. Switch to As-Is or Diff for observed modules and question candidates.</p>`;
      return;
    }
    const componentOrder = new Map(renderedScene.nodes.slice().sort((a, b) => positions[a.id].y - positions[b.id].y
      || positions[a.id].x - positions[b.id].x).map((node, index) => [node.id, index]));
    const modules = atlasExploreModules = REPORT_SCENE.atlasModules(level, S.view)
      .sort((a, b) => (componentOrder.get(a.component_id) ?? componentOrder.size) - (componentOrder.get(b.component_id) ?? componentOrder.size)
        || (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.name.localeCompare(b.name));
    const shown = S.allHints ? level.questions : level.questions.slice(0, 5);
    const titles = { used_elsewhere: "Used elsewhere", hub: "Hub", heavy: "Heavy", no_owner: "No owner" };
    explore.innerHTML = `${atlasBalanceMarkup(level)}${atlasFindingsMarkup(level, modules)}
      <div class="atlas-explore-heading"><h3>Worth a look</h3><span>${REPORT_SCENE.countLabel(modules.length, "module")} · ${REPORT_SCENE.countLabel(level.cells.length, "module dependency", "module dependencies")}</span></div>
      <p>Deterministic question candidates from Core, not verdicts. Thresholds remain provisional.</p>
      <ul class="atlas-questions">${shown.map((index) => {
        const hint = ATLAS.questions[index];
        const subject = hint.kind === "hub" ? ["importing module", "importing modules"]
          : hint.kind === "heavy" ? ["observed symbol", "observed symbols"]
            : hint.kind === "no_owner" ? ["authenticated owner", "authenticated owners"]
              : ["observed import site", "observed import sites"];
        return `<li><span class="atlas-chip">${titles[hint.kind]}</span> ${REPORT_SCENE.countLabel(hint.count, ...subject)}
          <p>${hint.module_ids.map((id) => `<code>${esc(REPORT_SCENE.atlasModuleById(id).name)}</code>`).join(", ")}</p><p>${esc(hint.question)}</p>
          <button type="button" data-show-question="${index}">Show in matrix</button> <button type="button" data-copy-question="${index}">Copy as question</button></li>`;
      }).join("") || '<li>No question candidates at this level.</li>'}</ul>
      ${level.questions.length > 5 ? `<button type="button" data-all-questions>${S.allHints ? "Show fewer" : `Show all ${level.questions.length} questions`}</button>` : ""}
      <h3>Module matrix</h3><p>Row imports column. Neutral: Core PASS · Red: Core FAIL · Amber: Core UNKNOWN.
      Module permission is never inferred from a declared requires edge.</p>
      <p class="atlas-coverage">${esc(level.import_status)}: ${esc(level.import_reason)}</p>
      <div class="flow-matrix" role="region" aria-label="Module import matrix" tabindex="0"></div>
      <details class="atlas-module-list"><summary>Modules and UML · ${modules.length}</summary></details>`;
    if (!level.questions.length) {
      explore.querySelector(".atlas-explore-heading").remove();
      explore.querySelector(".atlas-questions").previousElementSibling.remove();
      explore.querySelector(".atlas-questions").remove();
    }
    const list = explore.querySelector("details.atlas-module-list");
    list.addEventListener("toggle", () => {
      if (list.open && !list.querySelector("section")) list.insertAdjacentHTML("beforeend", atlasModuleList(level));
    });
    explore.querySelectorAll("[data-copy-question]").forEach((button) => button.onclick = () => copyAtlasQuestion(ATLAS.questions[Number(button.dataset.copyQuestion)], button));
    explore.querySelectorAll("[data-show-question]").forEach((button) => button.onclick = () =>
      dispatch({ type: "showHint", index: Number(button.dataset.showQuestion) }));
    const more = explore.querySelector("[data-all-questions]");
    if (more) more.onclick = () => dispatch({ type: "toggleAllHints" });
    if (S.explore) atlasMatrix(level, modules);
  }

  function atlasMatrixGeometry(matrix, modules) {
    const n = modules.length, requestedSize = Math.max(2.4, Math.min(16, 720 / Math.max(1, n)));
    const size = requestedSize >= 9 && requestedSize < 12 ? 12 : requestedSize;
    const groups = [];
    for (let start = 0; start < n;) {
      let end = start + 1;
      while (end < n && modules[end].component_id === modules[start].component_id) end++;
      groups.push({ start, end, name: modules[start].component_id
        ? `${REPORT_SCENE.atlasComponent(modules[start].component_id)?.label || "Component"} · inside` : "Root" });
      start = end;
    }
    const probe = el("text", { class: "matrix-group-label" });
    matrix.appendChild(probe);
    measureText.font = getComputedStyle(probe).font;
    const labelWidth = Math.max(120, ...groups.map((group, index) => {
      const range = `${group.start + 1}–${group.end}`;
      return Math.max(
        measureText.measureText(`${index + 1}. ${group.name} · columns ${range}`).width,
        measureText.measureText(`${index + 1}. ${group.name} · rows ${range}`).width,
      );
    }));
    probe.setAttribute("class", "matrix-label");
    measureText.font = getComputedStyle(probe).font;
    const margin = size < 9 ? 54 : Math.max(154, ...modules.map((module) =>
      measureText.measureText(module.name.split(".").slice(-2).join(".")).width + 12));
    probe.remove();
    const bandHeight = 28 + groups.length * 14, gridTop = margin + bandHeight;
    matrix.setAttribute("width", String(Math.max(margin + n * size + 12, margin + labelWidth * 2 + 20)));
    matrix.setAttribute("height", String(gridTop + n * size + 12));
    return { size, groups, margin, labelWidth, gridTop };
  }

  function atlasMatrix(level, modules) {
    const region = root.querySelector(".flow-matrix");
    if (!region || region.firstChild) return;
    const matrix = el("svg", {
      role: "img", "aria-label": `${REPORT_SCENE.countLabel(modules.length, "module")}. A row imports a column.` });
    region.appendChild(matrix);
    const { size, groups, margin, labelWidth, gridTop } = atlasMatrixGeometry(matrix, modules);
    const indexes = new Map(modules.map((module, index) => [module.id, index]));
    const columnHeading = el("text", { class: "matrix-axis-heading", x: String(margin), y: "14" });
    columnHeading.textContent = "Column groups · left to right"; matrix.appendChild(columnHeading);
    const rowHeading = el("text", { class: "matrix-axis-heading", x: String(margin + labelWidth + 20), y: "14" });
    rowHeading.textContent = "Row groups · top to bottom"; matrix.appendChild(rowHeading);
    groups.forEach((group, index) => {
      const y = String(28 + index * 14), range = `${group.start + 1}–${group.end}`;
      for (const [axis, x] of [["column", margin], ["row", margin + labelWidth + 20]]) {
        const label = el("text", { class: "matrix-group-label", "data-axis": axis, x: String(x), y });
        label.textContent = `${index + 1}. ${group.name} · ${axis === "column" ? "columns" : "rows"} ${range}`;
        matrix.appendChild(label);
      }
      matrix.appendChild(el("rect", { class: "matrix-block",
        x: String(margin + group.start * size), y: String(gridTop + group.start * size),
        width: String((group.end - group.start) * size), height: String((group.end - group.start) * size) }));
    });
    modules.forEach((module, index) => {
      if (size < 9) return;
      for (const column of [false, true]) {
        const label = el("text", { class: "matrix-label", "data-module": module.id, tabindex: "0", role: "button",
          x: String(column ? margin + (index + .5) * size : margin - 6),
          y: String(column ? gridTop - 6 : gridTop + (index + .7) * size), "text-anchor": column ? "start" : "end",
          ...(column ? { transform: `rotate(-90 ${margin + (index + .5) * size} ${gridTop - 6})` } : {}) });
        label.textContent = module.name.split(".").slice(-2).join(".");
        label.appendChild(el("title")); label.lastChild.textContent = module.name;
        matrix.appendChild(label);
      }
    });
    for (const index of level.cells) {
      const cell = ATLAS.cells[index], row = indexes.get(cell.source_id), column = indexes.get(cell.target_id);
      if (row === undefined || column === undefined) continue;
      const state = cell.status === "FAIL" ? "fail" : cell.status === "UNKNOWN" ? "unknown" : "pass";
      const rect = el("rect", { class: `matrix-cell ${state}${S.view === "diff" && cell.status !== "FAIL" ? " quiet" : ""}`,
        "data-cell": String(index), tabindex: "0", role: "button",
        "aria-label": `${modules[row].name} imports ${modules[column].name}: ${REPORT_SCENE.countLabel(cell.import_sites, "site")}; Core ${cell.status}; permission ${cell.permission}`,
        x: String(margin + column * size), y: String(gridTop + row * size), width: String(Math.max(2.4, size - 1)), height: String(Math.max(2.4, size - 1)) });
      const title = el("title"); title.textContent = rect.getAttribute("aria-label"); rect.appendChild(title); matrix.appendChild(rect);
    }
    const choose = (event) => {
      const cell = event.target.closest("[data-cell]"), module = event.target.closest("[data-module]");
      if (!cell && !module) return;
      dispatch({ type: "selectMatrix", cell: cell ? Number(cell.dataset.cell) : null, module: module?.dataset.module || null });
    };
    matrix.addEventListener("click", choose);
    matrix.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); choose(event); } });
    atlasHighlightQuestion();
  }

  function atlasHighlightQuestion() {
    const highlighted = new Set(S.hint === null ? [] : ATLAS.questions[S.hint].module_ids);
    root.querySelectorAll(".matrix-cell").forEach((rect) => {
      const cell = ATLAS.cells[Number(rect.dataset.cell)];
      rect.classList.toggle("highlighted", highlighted.has(cell.source_id) || highlighted.has(cell.target_id));
    });
  }
