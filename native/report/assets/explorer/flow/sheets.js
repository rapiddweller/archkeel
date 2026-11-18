  // The fact sheet of the selected box, module or import cell.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  function findingMarkup(findings) {
    return findings.length ? `<ul class="plain">${findings.map((item) => `<li class="${item.status === "FAIL" ? "violation-card" : "unknown-card"}"><strong>${esc(item.status)} · ${esc(item.title)}</strong><p><code>${item.rule_ids.map(esc).join(", ")}</code></p><p>${item.subjects.map(esc).join(", ")}</p></li>`).join("")}</ul>` : "<p>No recorded failures or UNKNOWN findings. This is not a completeness claim.</p>";
  }
  function atlasReferences(item, field) {
    return (item[field] || []).map((index) => ATLAS.reference_ids[index]);
  }
  function atlasFindings(level) {
    const ids = new Set((level.finding_ids || []).map((reference) => Number.isInteger(reference)
      ? ATLAS.findings[reference]?.id : reference));
    return (ATLAS.findings || []).filter((finding) => ids.has(finding.id));
  }
  function atlasRuleScopeHref(level, ruleId) {
    const query = new URLSearchParams(location.search);
    query.delete("component");
    if (level.parent_id) query.set("scope", level.parent_id);
    else query.delete("scope");
    query.set("view", S.view);
    return `${location.pathname}?${query}#atlas-rule-${encodeURIComponent(ruleId)}`;
  }
  // A finding count in plain words, from the phrase that the core page gives each rule kind.
  function atlasPlainFindings(ruleId, count) {
    const rule = (ATLAS.rule_assessments || []).find((item) => item.id === ruleId);
    const phrase = rule && (count === 1 ? rule.plain_one : rule.plain_many);
    return phrase ? `${count} ${phrase}` : REPORT_SCENE.countLabel(count, "finding");
  }
  // The anchor of the first violation block of a rule, on the page.
  function atlasFindingHref(findings, ruleId) {
    const found = findings.find((finding) => finding.rule_ids.includes(ruleId));
    return found ? `#${found.id}` : "";
  }
  function atlasRuleAssessmentMarkup(level, component = null) {
    const assessments = ATLAS.rule_assessments || [];
    const scopedLevel = component ? ATLAS.levels.find((item) => item.parent_id === component.id) : level;
    const findings = scopedLevel ? atlasFindings(scopedLevel) : [];
    const failureGroups = new Map();
    findings.forEach((finding) => finding.rule_ids.forEach((rule) =>
      failureGroups.set(rule, (failureGroups.get(rule) || 0) + 1)));
    const statuses = ["PASS", "FAIL", "UNKNOWN"].map((status) =>
      `${status} ${assessments.filter((item) => item.status === status).length}`).join(" · ");
    const notChecked = ATLAS.declared_rules === "NOT CHECKED" ? " · NOT CHECKED" : "";
    const recordedChecks = `<section class="atlas-scoped-findings"><h3>Recorded checks${component ? ` · ${esc(component.label)}` : ""}</h3>
      <p>${findings.length ? `${REPORT_SCENE.countLabel(findings.length, "finding")} recorded in this scope.` : (component ? "No violation in this component." : "No violation in this scope.")}</p>
      ${failureGroups.size ? `<ul class="plain">${[...failureGroups].map(([ruleId, count]) =>
      `<li><a href="${esc(atlasFindingHref(findings, ruleId) || atlasRuleScopeHref(scopedLevel || level, ruleId))}">${esc(atlasPlainFindings(ruleId, count))}</a> <small class="muted">(${esc(ruleId)})</small></li>`).join("")}</ul>` : ""}</section>`;
    if (component) return recordedChecks;
    return `${recordedChecks}<details class="atlas-rule-assessments"><summary>Rules · whole run ${esc(ATLAS.declared_rules || "NOT CHECKED")} · ${statuses}${notChecked}</summary>
      <p>Whole-run rule assessments; local findings are scoped separately above. Each UNKNOWN keeps its rule, reason and scope.</p>
      ${assessments.length ? `<ul class="plain">${assessments.map((item) => {
      const localCount = failureGroups.get(item.id) || 0;
      const rule = localCount
        ? `<a href="${esc(atlasRuleScopeHref(scopedLevel || level, item.id))}">${esc(item.id)}</a>`
        : `<code>${esc(item.id)}</code>`;
      const evidence = item.evidence.length
        ? `<ul>${item.evidence.map((entry) => `<li>${esc(entry.kind)} · ${esc(entry.title)} · ${esc(entry.subjects.join(", "))}${entry.subject_count > entry.subjects.length ? ` (+${entry.subject_count - entry.subjects.length} subjects in audit)` : ""}${entry.reason ? ` · ${esc(entry.reason)}` : ""} · record ${esc(entry.id)}</li>`).join("")}</ul>`
        : "";
      const scope = atlasComponentLink(item.scope_id, item.scope);
      const affected = item.component_ids.map((id) => {
        const component = ATLAS.components.find((entry) => entry.id === id);
        return atlasComponentLink(id, component?.scope || id);
      }).join(", ");
      const uncertainEvidence = item.status === "UNKNOWN" || item.undecided > 0
        ? `<p>Affected scope: ${scope}</p>${affected ? `<p>Affected components: ${affected}</p>` : ""}
          <p>Recorded uncertainty evidence: ${item.evidence.length} of ${item.evidence_count} records.</p>${evidence}
          ${item.uncertainty_actions.length ? `<ul>${item.uncertainty_actions.map((action) =>
            `<li data-uncertainty-cause="${esc(action.cause)}" data-architect-actionable="${action.architect_actionable ?? "unknown"}"><strong>${esc(action.cause.replaceAll("_", " "))}</strong> · ${action.architect_actionable === true ? "Architect decision required" : action.architect_actionable === false ? "Evidence or analysis action required" : "Architect actionability not established"}: ${esc(action.next_action)}</li>`).join("")}</ul>`
            : "<p>Next action: inspect the recorded reason and affected scope. No cause was established for this uncertainty.</p>"}
          ${auditInstructions()}` : "";
      return `<li id="atlas-assessment-${esc(item.id)}" tabindex="-1"><strong class="atlas-rule-status ${esc(item.status.toLowerCase())}">${esc(item.status)}</strong> · ${rule} (${esc(item.kind)}) · ${scope} · ${esc(item.reason)}`
        + `${item.count ? ` · ${REPORT_SCENE.countLabel(item.count, "recorded result")}` : ""}`
        + `${item.undecided ? ` · ${REPORT_SCENE.countLabel(item.undecided, "undecided result")}` : ""}`
        + `${uncertainEvidence}</li>`;
      }).join("")}</ul>` : "<p>Rule assessments were not recorded.</p>"}</details>`;
  }
  function auditInstructions() {
    return `<p>To generate the full audit JSON, run <code>archkeel report --topology --output report.json --format json</code> with the same root and configuration. A new run reads the current source; it may differ from this report.</p>`;
  }

  function atlasEvidenceMarkup() {
    if (!ATLAS.unknowns.length) return "";
    if (ATLAS.gap_messages_complete !== true) return `<section class="atlas-evidence"><h3>Analysis limits</h3>
      <p>This older report stores shortened messages. Their full text is unavailable here.</p>${auditInstructions()}</section>`;
    const ranked = [...ATLAS.unknowns].sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
    return `<section class="atlas-evidence"><h3>Analysis limits</h3>
      <p>${REPORT_SCENE.countLabel(ATLAS.unknown_count, "gap record")} · ${REPORT_SCENE.countLabel(ranked.length, "distinct message")}. These counts are not rule verdicts or independent causes. Not every gap holds every rule.</p>
      ${(ATLAS.whole_scan_holds || []).slice(0, 3).map((hold) => `<p>${REPORT_SCENE.countLabel(hold.rules, "UNKNOWN rule")} ${hold.rules === 1 ? "reports" : "each report"} ${REPORT_SCENE.countLabel(hold.gaps, "whole-scan gap")}. Gap counts can overlap between rules; they are not added.</p>`).join("")}
      ${(ATLAS.whole_scan_holds || []).length > 3 ? "<p>See Rules above for the other rule verdicts.</p>" : ""}
      <p>Most frequent messages:</p><ul class="plain">${ranked.slice(0, 3).map(atlasGapMessage).join("")}</ul>
      <details data-gap-search><summary>Search all ${ranked.length} distinct messages</summary>
        <label>Search messages <input type="search" data-gap-query></label>
        <p data-gap-count aria-live="polite"></p><ul class="plain" data-gap-results></ul>
        <button type="button" data-gap-previous>Previous</button> <button type="button" data-gap-next>Next</button>
      </details>${auditInstructions()}</section>`;
  }
  function atlasGapMessage(item) {
    return `<li><strong>${REPORT_SCENE.countLabel(item.count, "gap record")}</strong> · ${esc(item.reason)}${item.example ? `<br>Example: <code>${esc(item.example)}</code>` : ""}</li>`;
  }
  function wireGapSearch() {
    const section = inspectorContent.querySelector("[data-gap-search]");
    if (!section) return;
    const query = section.querySelector("[data-gap-query]");
    const previous = section.querySelector("[data-gap-previous]");
    const next = section.querySelector("[data-gap-next]");
    let offset = 0;
    const draw = () => {
      const term = query.value.toLocaleLowerCase();
      const rows = ATLAS.unknowns.filter((item) => `${item.reason} ${item.example}`.toLocaleLowerCase().includes(term))
        .sort((a, b) => b.count - a.count || a.reason.localeCompare(b.reason));
      section.querySelector("[data-gap-count]").textContent = `${REPORT_SCENE.countLabel(rows.length, "matching message")} · showing ${rows.length ? offset + 1 : 0}–${Math.min(offset + 20, rows.length)}`;
      section.querySelector("[data-gap-results]").innerHTML = rows.slice(offset, offset + 20).map(atlasGapMessage).join("");
      previous.disabled = offset === 0;
      next.disabled = offset + 20 >= rows.length;
    };
    query.addEventListener("input", () => { offset = 0; draw(); });
    previous.onclick = () => { offset = Math.max(0, offset - 20); draw(); };
    next.onclick = () => { offset += 20; draw(); };
    draw();
  }

  function moduleInventoryMarkup(inventories) {
    const plannedFiles = inventories.flatMap((item) => item.modules);
    return `<section class="flow-module-inventory">${plannedFiles.length ? `<details><summary>Module inventory · ${REPORT_SCENE.countLabel(plannedFiles.length, "planned file")}</summary>
      <p>File intent does not define classes, methods, imports or calls.</p>${S.view !== "target" ? "<p>Observed file presence is separate from a Core verdict.</p>" : ""}<ul class="plain">${plannedFiles.map((item) => {
        const actual = S.view === "target" ? null : DATA.observed?.entities.find((entity) => entity.kind === "module" && entity.presence === "defined" && entity.file_path === item.path);
        const findings = (S.view === "target" ? [] : DATA.findings || []).filter((finding) => finding.subjects.includes(item.path));
        return `<li data-file-intent="${esc(item.path)}"><code>${esc(item.path)}</code><p>${esc(item.responsibility)}</p>${S.view !== "target" ? `<p>${DATA.observed ? actual ? `Observed module: ${esc(actual.qualified_name)}` : "Not in the observed file inventory." : "Source facts are unavailable."}</p>` : ""}${findings.length ? findingMarkup(findings) : ""}</li>`;
      }).join("")}</ul></details>` : `<h3>Module inventory</h3><p>${inventories.length ? "Explicitly empty" : "Not declared"}</p>`}
      <p>${[...new Set(inventories.flatMap((item) => item.provenance))].map(esc).join(" · ")}</p></section>`;
  }

  // The symbols of a module: the count when the run has one, else the limit in plain words, once.
  // The coverage record states it (`unavailable` and its reason); nothing is said when it states none.
  function atlasSymbolsLine(module) {
    if (module.symbols != null) return REPORT_SCENE.countLabel(module.symbols, "observed symbol");
    const limit = (module.symbol_coverage || []).find((item) => item.status === "unavailable");
    if (!limit) return "";
    const reason = (limit.reason || "").replace(/\.$/, "");
    return `Symbols: not counted${reason ? ` (${esc(reason.charAt(0).toLowerCase() + reason.slice(1))})` : ""}`;
  }
  // A box that holds one component is that component, whatever its id says.
  function atlasBoxHoldsOneComponent(component) {
    return component.groups === null || component.groups === undefined || component.groups === 1;
  }
  // What a box is: a layer or a group of components, or a component.
  function atlasBoxKind(component) {
    if (component.directory) return "Directory";
    if (atlasBoxHoldsOneComponent(component)) return "Component";
    return component.layer_rank !== null && component.layer_rank !== undefined ? "Layer" : "Group";
  }
  // The public names of a box, grouped by module with short names and a count. The module paths lose
  // the part that they all share. Many names fold behind the line that counts them.
  function atlasProvidesMarkup(names) {
    if (!names || !names.length) return "";
    const byModule = new Map();
    for (const name of names) {
      const at = name.lastIndexOf(":");
      const module = at < 0 ? "" : name.slice(0, at), short = at < 0 ? name : name.slice(at + 1);
      if (!byModule.has(module)) byModule.set(module, []);
      byModule.get(module).push(short);
    }
    const paths = [...byModule.keys()].map((path) => path.split("."));
    let shared = 0;
    while (paths.length && paths.every((parts) => parts.length > shared + 1 && parts[shared] === paths[0][shared])) shared += 1;
    const rows = [...byModule].map(([module, shorts]) => {
      const label = module ? module.split(".").slice(shared).join(".") || module : "";
      // Every name is listed: the fold above the list opens to the whole interface.
      return `<li>${label ? `<strong>${esc(label)}</strong> (${shorts.length}): ` : ""}${shorts.map(esc).join(", ")}</li>`;
    }).join("");
    const title = `Provides · ${REPORT_SCENE.countLabel(names.length, "name")}${byModule.size > 1 ? ` in ${REPORT_SCENE.countLabel(byModule.size, "module")}` : ""}`;
    return names.length > 6 ? `<details class="atlas-provides"><summary>${title}</summary><ul class="plain">${rows}</ul></details>`
      : `<h3>${title}</h3><ul class="plain">${rows}</ul>`;
  }
  // What a component owns, as one short line: one package or module is named, many are counted.
  function atlasOwnsMarkup(path) {
    const parts = path.split(", ");
    return parts.length === 1 ? `<p class="muted">Owns <code>${esc(parts[0])}</code></p>`
      : `<details class="atlas-owns"><summary>owns ${REPORT_SCENE.countLabel(parts.length, "package or module", "packages and modules")}</summary><p>${parts.map(esc).join(", ")}</p></details>`;
  }
  // The declared dependencies of a component: one line each, the way through folded behind a count.
  function atlasRequiresMarkup(component) {
    if (!component.requires.length) return "";
    const rows = component.requires.map((edge) => {
      const through = edge.through.length > 2
        ? `<details><summary>through ${REPORT_SCENE.countLabel(edge.through.length, "path")}</summary><p>${edge.through.map(esc).join(", ")}</p></details>`
        : edge.through.length ? `<p class="muted">through ${edge.through.map(esc).join(", ")}</p>` : "";
      const seen = S.view !== "target" ? ` · ${REPORT_SCENE.countLabel(edge.observed_imports, "observed import")}` : "";
      return `<li><strong>${esc(REPORT_SCENE.atlasComponent(edge.target_id)?.label || edge.target_id)}</strong>${seen}<p>${esc(edge.rationale)}</p>${through}</li>`;
    }).join("");
    return `<details class="atlas-requires"><summary>Requires · ${REPORT_SCENE.countLabel(component.requires.length, "declared dependency", "declared dependencies")}</summary><ul class="plain">${rows}</ul></details>`;
  }
  function atlasSheet(level, scene = renderedScene) {
    const component = REPORT_SCENE.atlasComponent(S.selection?.id || level.parent_id);
    const inventory = S.view === "target" ? moduleInventoryMarkup(ATLAS.module_inventories
      .filter((item) => item.component_id === (component?.id || null))) : "";
    const entries = (items) => items ? items.map((item) => `<li>${esc(item)}</li>`).join("") : "";
    const list = (title, items) => items && items.length ? `<h3>${title}</h3><ul class="plain">${entries(items)}</ul>` : "";
    if (S.view !== "target" && S.cell !== null) {
      const cell = ATLAS.cells[S.cell];
      const source = REPORT_SCENE.atlasModuleById(cell.source_id), target = REPORT_SCENE.atlasModuleById(cell.target_id);
      inspectorContent.innerHTML = `<div class="kicker">Observed import cell</div><h2>${esc(source.name)} → ${esc(target.name)}</h2>
        <p>${atlasModuleLink(source, `Show ${source.name}`)}</p>
        <p>${cell.import_sites ?? "UNKNOWN"} import sites · Core finding status: <strong>${esc(cell.status)}</strong></p>
        <p>Permission: <strong>${esc(cell.permission)}</strong></p><p>${esc(cell.permission_reason)}</p>
        ${list("Recorded reasons", cell.reasons)}${list("Finding IDs", atlasReferences(cell, "finding_ids"))}
        ${list("Evidence IDs", atlasReferences(cell, "evidence_ids"))}`;
      return;
    }
    if (S.view !== "target" && S.module) {
      const module = REPORT_SCENE.atlasModuleById(S.module);
      const assignment = ATLAS.assignments.find((item) => item.id === module.id);
      const owner = REPORT_SCENE.atlasComponent(assignment?.component_id);
      const grouped = (direction) => {
        const rows = ATLAS.cells.filter((cell) => cell[direction === "in" ? "target_id" : "source_id"] === module.id);
        const groups = new Map();
        let outside = 0;
        for (const cell of rows) {
          const id = cell[direction === "in" ? "source_id" : "target_id"];
          const other = REPORT_SCENE.atlasModuleById(id);
          const binding = ATLAS.assignments.find((item) => item.id === id);
          const known = REPORT_SCENE.atlasComponent(binding?.component_id)?.label;
          // A module that no component owns is no component: it is counted apart.
          if (!known) outside += 1;
          const name = known || "Outside the contract";
          if (!groups.has(name)) groups.set(name, []);
          groups.get(name).push(`<li>${esc(other.name)} · ${REPORT_SCENE.countLabel(cell.import_sites, "site")}</li>`);
        }
        if (!rows.length) return "";
        // Many modules fold behind the line that counts them, as the provided names do.
        const components = groups.size - (outside ? 1 : 0);
        const counted = [components ? `${REPORT_SCENE.countLabel(rows.length - outside, "module")} in ${REPORT_SCENE.countLabel(components, "component")}` : "",
          outside ? `${REPORT_SCENE.countLabel(outside, "module")} outside the contract` : ""].filter(Boolean).join(" · ");
        const title = `${direction === "in" ? "Imported by" : "Imports"} · ${counted}`;
        const body = [...groups].map(([name, items]) => `<h4>${esc(name)}</h4><ul class="plain">${items.join("")}</ul>`).join("");
        return rows.length > 4 ? `<details class="atlas-imports"><summary>${title}</summary>${body}</details>` : `<h3>${title}</h3>${body}`;
      };
      inspectorContent.innerHTML = `<div class="kicker">Observed module · counts over the observed source scope</div>
        <h2>${esc(module.name)}</h2>${atlasModuleShown(module.id) ? "" : `<p>${atlasModuleLink(module, "Show in the module view")}</p>`}${module.path ? `<p><code>${esc(module.path)}</code></p>` : ""}
        <p>${atlasSymbolsLine(module)}</p>
        <p>fan-in ${module.fan_in ?? "UNKNOWN"} · fan-out ${module.fan_out ?? "UNKNOWN"}</p>
        <h3>Owner</h3><p>${esc(owner?.label || "UNKNOWN")} · ${esc(assignment?.ownership_reason || "No assignment receipt")}</p>
        ${owner ? list("Responsibility", owner.responsibilities) + list("Not responsible for", owner.not_responsible_for) : list("Candidate owners", assignment?.candidate_ids || [])}
        ${grouped("in")}${grouped("out")}
        ${boundaryPermissionMarkup(module.id, new Set([module.id]))}`;
      return;
    }
    if (S.view === "target") {
      const module = REPORT_SCENE.atlasModules(level, S.view).find((item) => item.id === S.selection?.id);
      if (module) {
        inspectorContent.innerHTML = `<div class="kicker">Declared module</div><h2>${esc(module.name)}</h2>
          ${atlasModuleShown(module.id) ? "" : `<p>${atlasModuleLink(module, "Show in the module view")}</p>`}<p><code>${esc(module.path || "File path not declared")}</code></p>
          <p>${REPORT_SCENE.countLabel(module.declarations, "direct declared definition")}</p>${list("Responsibility", module.responsibilities)}${list("Provenance", module.provenance)}
          ${boundaryPermissionMarkup(module.id, new Set([module.id]))}
          ${list("Authored module relationships", scene.edges.filter((edge) => edge.source === module.id || edge.target === module.id)
            .map((edge) => `${edge.id} · ${edge.relationshipKind}: ${edge.source} → ${edge.target} · ${edge.declaration.evidence_ids.join(", ")}`))}`;
        return;
      }
    }
    if (!component) {
      inspectorContent.innerHTML = `<div class="kicker">Fact sheet${S.view === "target" ? " · Declared intent" : ""}</div><h2>${esc(ATLAS.repository)}</h2>
        <p>${S.view === "target" ? "Select a component or declared module." : "Select a component, module, import cell or question."}</p>
        ${inventory}${boundaryPermissionMarkup()}
        ${S.view === "target" ? "" : `${atlasRuleAssessmentMarkup(level)}${atlasEvidenceMarkup()}`}
        ${auditInstructions()}`;
      wireGapSearch();
      return;
    }
    const componentLevel = ATLAS.levels.find((item) => item.parent_id === component.id);
    const moduleCount = componentLevel ? REPORT_SCENE.atlasModules(componentLevel, S.view).length : 0;
    const usedBy = component.used_by.map((item) => `${esc(REPORT_SCENE.atlasComponent(item.component_id)?.label || item.component_id)} (${item.import_sites})`).join(", ");
    inspectorContent.innerHTML = `<div class="kicker">${atlasBoxKind(component)} fact sheet · ${S.view === "target" ? "Declared intent" : "Core facts"}</div>
      ${boundaryPermissionMarkup(component.id)}<h2>${esc(component.label)}</h2><p><button type="button" class="flow-fit" data-browse-component>${moduleCount ? `Browse ${REPORT_SCENE.countLabel(moduleCount, "module")}` : `Browse ${esc(component.label)}`}</button>${component.layer ? ` <span class="muted">layer ${esc(component.layer)}</span>` : ""}</p>${list(component.directory ? "About" : "Responsibility", component.responsibilities)}
      ${list("Not responsible for", component.not_responsible_for)}${atlasProvidesMarkup(component.public)}
      ${list("Planned interface", component.planned)}${atlasRequiresMarkup(component)}
      ${S.view === "target" ? "" : atlasRuleAssessmentMarkup(level, component)}${S.view !== "target" ? `<h3>In this run</h3><p>${REPORT_SCENE.countLabel(component.observed_modules, "module")}${component.observed_symbols == null ? "" : ` · ${REPORT_SCENE.countLabel(component.observed_symbols, "observed symbol")}`} · ${esc(component.status)} · ${esc(component.reason)}</p>${usedBy ? `<h3>Used by</h3><p>${usedBy}</p>` : ""}` : ""}
      <p class="muted">${component.directory ? `The report made this box from the module paths; ${esc(REPORT_SCENE.atlasComponent(component.parent_id)?.label || component.parent_id)} owns the modules in the contract.` : component.decided_by === "report" ? "Grouped by the report (structure): the report made this box to keep the level readable. Each component inside keeps its own decisions in the contract." : `Decided by ${esc(component.decided_by || "the contract")}`}</p>${S.view === "target" || !component.path || component.directory ? "" : atlasOwnsMarkup(component.path)}
      ${component.provenance.length ? `<details><summary>Reasons · ${REPORT_SCENE.countLabel(component.provenance.length, "document")}</summary><ul class="plain">${component.provenance.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></details>` : ""}${inventory}
      ${S.view === "target" && componentLevel ? `<p><a href="${esc(atlasLevelHref(component.id))}" data-atlas-level-route="${esc(component.id)}">Open declared component details</a></p>` : ""}`;
    inspectorContent.querySelector("[data-browse-component]").onclick = () =>
      dispatch({ type: "openLevel", id: component.id, content: "modules" });
  }
