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

  const MATRIX_LIMIT = 60;
  function setAtlasExploreOpen(open) {
    S.explore = open;
  }

  function atlasExplore(level) {
    const explore = root.querySelector(".flow-explore");
    if (S.view === "target") {
      explore.innerHTML = `${atlasFindingsMarkup(level, REPORT_SCENE.atlasModules(level, S.view))}<h3>Explore</h3><p>Target shows declarations only. Switch to As-Is or Diff for observed modules and question candidates.</p>`;
      return;
    }
    const componentOrder = new Map(renderedScene.nodes.slice().sort((a, b) => positions[a.id].y - positions[b.id].y
      || positions[a.id].x - positions[b.id].x).map((node, index) => [node.id, index]));
    const modules = REPORT_SCENE.atlasModules(level, S.view)
      .sort((a, b) => (componentOrder.get(a.component_id) ?? componentOrder.size) - (componentOrder.get(b.component_id) ?? componentOrder.size)
        || (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.name.localeCompare(b.name));
    const large = modules.length > MATRIX_LIMIT;
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
          <button type="button" data-show-question="${index}">${large ? "Show module details" : "Show in matrix"}</button> <button type="button" data-copy-question="${index}">Copy as question</button></li>`;
      }).join("") || '<li>No question candidates at this level.</li>'}</ul>
      ${level.questions.length > 5 ? `<button type="button" data-all-questions>${S.allHints ? "Show fewer" : `Show all ${level.questions.length} questions`}</button>` : ""}
      <h3>Module dependencies</h3><p>This level has ${modules.length} modules. Open the matrix to see observed imports${large ? " grouped by the existing hierarchy" : ""}.</p>
      <p class="atlas-coverage">${esc(level.import_status)}: ${esc(level.import_reason)}</p>
      <button type="button" data-open-matrix>Open dependency matrix</button>
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
    explore.querySelectorAll("[data-show-question]").forEach((button) => button.onclick = () => {
      dispatch({ type: "showHint", index: Number(button.dataset.showQuestion) });
      if (!large) atlasGroupedMatrix(level, modules);
    });
    const more = explore.querySelector("[data-all-questions]");
    if (more) more.onclick = () => dispatch({ type: "toggleAllHints" });
    explore.querySelector("[data-open-matrix]").onclick = () => atlasGroupedMatrix(level, modules);
  }

  function atlasGroupedMatrix(level, modules) {
    const nodes = modules.length <= MATRIX_LIMIT
      ? modules.map((module) => ({ id: module.id, label: module.name }))
      : REPORT_SCENE.atlasModuleScene(level, S.view).nodes;
    const ids = new Set(nodes.map((node) => node.id));
    const byModule = new Map(modules.map((module) => [module.id, module]));
    const group = new Map(modules.map((module) => [module.id,
      REPORT_SCENE.componentRoute(module.place_id || module.component_id)
        .find((item) => ids.has(item.id))?.id || module.id]));
    const positions = new Map(nodes.map((node, index) => [node.id, index]));
    const pairs = new Map();
    for (const index of nodes.length > MATRIX_LIMIT ? [] : level.cells) {
      const cell = ATLAS.cells[index], row = positions.get(group.get(cell.source_id));
      const column = positions.get(group.get(cell.target_id));
      if (row === undefined || column === undefined) continue;
      if (!pairs.has(row)) pairs.set(row, new Map());
      const columns = pairs.get(row);
      if (!columns.has(column)) columns.set(column, []);
      columns.get(column).push(index);
    }
    const dialog = document.createElement("dialog");
    dialog.className = "atlas-matrix-dialog";
    dialog.setAttribute("aria-label", "Dependency matrix");
    dialog.innerHTML = `<button type="button" class="atlas-matrix-close">Back to report</button>
      <h2>Dependency matrix</h2><p>Rows import columns.</p>
      <p>${esc(level.import_status)}: ${esc(level.import_reason)}</p>
      <details><summary>Reading guide</summary>
        <p>Numbers count observed module relationships. An empty position does not prove that an import is excluded.
        Select a number to see its module relationships.</p>
        <p>For one module relationship, red marks Core FAIL and amber marks Core UNKNOWN. Grouped cells show counts only.</p>
      </details>
      <div class="atlas-matrix-grid" role="region" aria-label="Grouped dependencies" tabindex="0"></div>
      <section class="atlas-matrix-detail" hidden></section>`;
    root.appendChild(dialog);
    dialog.querySelector(".atlas-matrix-close").onclick = () => dialog.close();
    dialog.addEventListener("close", () => dialog.remove(), { once: true });
    const grid = dialog.querySelector(".atlas-matrix-grid");
    if (nodes.length > MATRIX_LIMIT) {
      grid.textContent = `This level has ${nodes.length} groups. Go back and open a smaller component in the Explorer.`;
      dialog.querySelector(".atlas-matrix-detail").hidden = true;
      dialog.showModal();
      return;
    }
    const name = (node) => byModule.get(node.id)?.name || node.label;
    const wrappedName = (node) => esc(name(node)).replace(/[._]/g, "$&<wbr>");
    const heading = (node) => byModule.has(node.id)
      ? `<button type="button" class="atlas-matrix-module" data-module="${esc(node.id)}">${wrappedName(node)}</button>`
      : wrappedName(node);
    const highlighted = new Set(S.hint === null ? [] : ATLAS.questions[S.hint].module_ids);
    grid.innerHTML = `<table class="atlas-matrix-table"><thead><tr><th scope="col">Row imports column</th>
      ${nodes.map((node, index) => `<th scope="col" data-column="${index}">${heading(node)}</th>`).join("")}</tr></thead>
      <tbody>${nodes.map((node, row) => `<tr><th scope="row" data-row="${row}">${heading(node)}</th>
        ${nodes.map((target, column) => {
          const indexes = pairs.get(row)?.get(column);
          const mark = indexes?.some((index) => highlighted.has(ATLAS.cells[index].source_id)
            || highlighted.has(ATLAS.cells[index].target_id));
          return indexes ? `<td><button type="button" class="matrix-cell${mark ? " highlighted" : ""}" data-row="${row}" data-column="${column}"
            ${indexes.length === 1 ? `data-cell="${indexes[0]}"` : ""}
            ${indexes.length === 1 ? `data-status="${esc(ATLAS.cells[indexes[0]].status)}"` : ""}
            aria-label="${esc(name(node))} imports ${esc(name(target))}: ${REPORT_SCENE.countLabel(indexes.length, "module relationship")}">${indexes.length}</button></td>` : "<td></td>";
        }).join("")}</tr>`).join("")}</tbody></table>`;
    const detail = dialog.querySelector(".atlas-matrix-detail");
    grid.addEventListener("click", (event) => {
      const module = event.target.closest("button[data-module]");
      if (module) {
        dispatch({ type: "selectMatrix", cell: null, module: module.dataset.module });
        dialog.close();
        return;
      }
      const cell = event.target.closest("button[data-row]");
      if (!cell) return;
      const row = Number(cell.dataset.row), column = Number(cell.dataset.column);
      const indexes = pairs.get(row).get(column);
      detail.dataset.row = String(row); detail.dataset.column = String(column);
      detail.innerHTML =
        `<button type="button" class="atlas-matrix-back">Back to matrix</button>
        <h3>${esc(name(nodes[row]))} imports ${esc(name(nodes[column]))}</h3><ul>${indexes.map((index) => {
          const item = ATLAS.cells[index], source = byModule.get(item.source_id), target = byModule.get(item.target_id);
          return `<li>${esc(source.name)} → ${esc(target.name)} · ${REPORT_SCENE.countLabel(item.import_sites, "site")} · Core ${esc(item.status)}</li>`;
        }).join("")}</ul>`;
      if (indexes.length === 1) dispatch({ type: "selectMatrix", cell: indexes[0], module: null });
      grid.hidden = true; detail.hidden = false;
      detail.querySelector(".atlas-matrix-back").onclick = () => {
        detail.hidden = true; grid.hidden = false; cell.focus({ preventScroll: true });
      };
      detail.querySelector(".atlas-matrix-back").focus({ preventScroll: true });
    });
    grid.addEventListener("keydown", (event) => {
      const cell = event.target.closest("button[data-row]");
      if (cell && ["Enter", " "].includes(event.key)) { event.preventDefault(); cell.click(); }
    });
    dialog.showModal();
  }
