"use strict";
(function (global) {
  function create(data) {
    const nativeGraph = ArchkeelGraphScene.create(data);
    const ATLAS = data.atlas ? structuredClone(data.atlas) : null;
    const deviationIndex = ATLAS ? ArchkeelAtlasDeviations.create(ATLAS.deviations || []) : null;
    const DATA = { ...data, atlas: ATLAS };
    const NAV = DATA.navigation || null;
    const countLabel = (value, singular, plural = `${singular}s`) =>
      value === null || value === undefined ? (singular.endsWith("symbol") ? "no symbol count in this run" : `UNKNOWN ${plural}`) : `${value} ${value === 1 ? singular : plural}`;
    // The core writes each repeated value once (the page budget): the declared boundary permissions
    // as one row for each `requires`, and no field that is the same for each module or edge. This
    // restores the full rows that the Explorer reads.
    const declared = data.boundary_permissions?.requires || [];
    const boundaryPermissions = {
      applied: data.boundary_permissions?.applied || [],
      declared: declared.flatMap(([source, target, rationale, selectors]) => selectors.map((name, n) => ({
        id: `PORT:${source}>${target}:${n}`, rule_id: "requires", component_ids: [source, target],
        qualified_name: name, position: `through, ${source} to ${target}`,
        rationale: ATLAS.reference_ids[rationale], decided_by: "architect", source: "contract",
        contract_scope_id: null, rule_ids: [], fact_ids: [], evidence_ids: [], provenance: [], locations: [], routes: [],
      }))),
    };
    if (ATLAS) {
      ATLAS.modules = ATLAS.modules.map((module) => ({
        name: module.id, ...module, rank: null, evidence_ids: [], symbol_coverage: 0, symbols: null,
      }));
      ATLAS.rule_assessments = (ATLAS.rule_assessments || []).map((item) => ({
        ...item,
        id: ATLAS.reference_ids[item.id], kind: ATLAS.reference_ids[item.kind],
        reason: ATLAS.reference_ids[item.reason], scope: ATLAS.reference_ids[item.scope],
        components: item.components.map((index) => ATLAS.reference_ids[index]),
        uncertainty_actions: (item.uncertainty_actions || []).map((action) => ({
          ...action, next_action: ATLAS.reference_ids[action.next_action],
        })),
        evidence: item.evidence.map((entry) => ({
          ...entry, id: ATLAS.reference_ids[entry.id],
        })),
      }));
      ATLAS.cells = ATLAS.cells.map(([source, target, count, status, evidence, findings, reasons]) => ({
        source_id: ATLAS.modules[source].id, target_id: ATLAS.modules[target].id, import_sites: count,
        status, permission: "UNKNOWN", permission_reason: ATLAS.reference_ids[ATLAS.cell_permission_reason_ref],
        evidence_ids: evidence, finding_ids: findings,
        reasons: reasons.map((index) => ATLAS.reference_ids[index]),
      }));
      ATLAS.assignments = ATLAS.assignments.map(([module, owner, candidates, status, reason, place]) => ({
        id: ATLAS.modules[module].id, component_id: owner === null ? null : ATLAS.reference_ids[owner],
        place_id: place === null || place === undefined ? null : ATLAS.reference_ids[place],
        candidate_ids: candidates.map((index) => ATLAS.reference_ids[index]),
        ownership_status: status, ownership_reason: ATLAS.reference_ids[reason],
      }));
      for (const module of ATLAS.modules) module.symbol_coverage = ATLAS.symbol_coverages[module.symbol_coverage]
        .map((entry) => ({ ...entry, scope_id: module.id }));
      for (const level of ATLAS.levels) level.modules = level.modules.map((index) => ATLAS.assignments[index]);
      for (const component of ATLAS.components) {
        component.reason = ATLAS.reference_ids[component.reason_ref];
        component.provenance = component.provenance.map((index) => ATLAS.reference_ids[index]);
        if (component.public !== null) component.public = component.public.map((index) => ATLAS.reference_ids[index]);
        component.used_by = component.used_by.map(([index, import_sites]) => ({
          component_id: ATLAS.components[index].id, import_sites,
        }));
        component.requires = component.requires.map((edge) => ({
          id: `REQ:${component.id}>${ATLAS.components[edge.target_id].id}`, decided_by: "architect",
          ...edge, target_id: ATLAS.components[edge.target_id].id,
          rationale: ATLAS.reference_ids[edge.rationale_ref],
        }));
      }
      for (const finding of ATLAS.findings) {
        if (Number.isInteger(finding.remedy_ref)) finding.remedy = ATLAS.reference_ids[finding.remedy_ref];
      }
    }
    function componentRoute(id) {
      const components = ATLAS?.components || NAV?.component_path || [];
      const path = [];
      let component = components.find((item) => item.id === id);
      while (component) {
        path.unshift(component);
        component = components.find((item) => item.id === component.parent_id);
      }
      return path;
    }

    function atlasComponent(id) { return ATLAS?.components.find((item) => item.id === id); }
    function atlasModuleById(id) { return ATLAS?.modules.find((item) => item.id === id); }

    function atlasModules(level, viewMode) {
      const modules = viewMode === "target" ? ATLAS.declared_modules.filter((module) => !level.parent_id
        || componentRoute(module.component_id).some((item) => item.id === level.parent_id))
        : level.modules.map((assignment) => ({ ...atlasModuleById(assignment.id), ...assignment }));
      return modules.slice().sort((a, b) => (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.name.localeCompare(b.name));
    }

    // One screen shows about this many module boxes (issue 1488); the report states the number.
    const MODULE_BOX_LIMIT = ATLAS?.module_box_limit;
    // The box of a module on the map: a directory box inside its owner, or the owner.
    const placeOf = (module) => module.place_id || module.component_id;
    // A deep path keeps its first directory and its last two parts: the file name stays readable.
    const shortPath = (path) => {
      const parts = path.split("/");
      return parts.length > 4 ? [parts[0], "…", ...parts.slice(-2)].join("/") : path;
    };

    // The child of the level that holds the module, or null when the level itself owns it.
    function childOwner(level, module) {
      const route = componentRoute(placeOf(module));
      const at = level.parent_id ? route.findIndex((item) => item.id === level.parent_id) + 1 : 0;
      return at > 0 || !level.parent_id ? route[at] || null : null;
    }

    // Too many modules for one screen: one box per child component with its module count. A
    // drill into a box shows its modules; the search and the module list reach one module.
    function groupedModuleScene(level, viewMode, modules) {
      const groupOf = new Map(), members = new Map(), loose = [];
      for (const module of modules) {
        const owner = childOwner(level, module);
        if (!owner) { loose.push(module); continue; }
        groupOf.set(module.id, owner.id);
        if (!members.has(owner.id)) members.set(owner.id, { component: owner, modules: [] });
        members.get(owner.id).modules.push(module);
      }
      const nodes = [...members.values()].map(({ component, modules: inside }) => ({
        id: component.id, label: component.label, kind: component.directory ? "package" : "component", component, group: inside.length,
        entity: null, sourceGraph: null, sections: [], outside: false,
        meta: "Open the box to see its modules.",
        tooltip: `${component.label}: ${countLabel(inside.length, "module")}`,
      })).concat(loose.map((module) => ({
        id: module.id, label: module.path?.split("/").at(-1) || module.name, kind: "module", module,
        entity: null, sourceGraph: null, sections: [], outside: false,
        meta: module.path ? shortPath(module.path) : "File path not declared", tooltip: module.path || module.name,
      })));
      const boxOf = (id) => groupOf.get(id) || id, shown = new Set(nodes.map((node) => node.id));
      const pairs = new Map();
      const add = (source, target, sites, status) => {
        const [from, to] = [boxOf(source), boxOf(target)];
        if (from === to || !shown.has(from) || !shown.has(to)) return;
        const key = `${from}\0${to}`, pair = pairs.get(key) || { source: from, target: to, sites: 0, status: "PASS" };
        pair.sites = pair.sites === null || sites === null || sites === undefined ? null : pair.sites + sites;
        if (status === "FAIL" || status === "UNKNOWN" && pair.status !== "FAIL") pair.status = status;
        pairs.set(key, pair);
      };
      if (viewMode === "target") {
        for (const module of ATLAS.declared_modules) for (const edge of module.relationships || [])
          add(module.id, edge.target_id, 0, "PASS");
      } else {
        for (const index of level.cells) {
          const cell = ATLAS.cells[index];
          add(cell.source_id, cell.target_id, cell.import_sites, cell.status);
        }
      }
      const edges = [...pairs.values()].map((pair) => ({
        id: `module-group:${pair.source}>${pair.target}`, source: pair.source, target: pair.target,
        kind: "dependency", relationshipKind: viewMode === "target" ? "requires" : "imports",
        state: viewMode === "target" ? "declared" : pair.status === "FAIL" ? "violation" : pair.status === "UNKNOWN" ? "undecided" : "observed",
        import_sites: viewMode === "target" ? undefined : pair.sites,
        label: viewMode === "target" ? "relationships" : countLabel(pair.sites, "import"),
        tooltip: viewMode === "target" ? "Authored module relationships between the two groups."
          : `${pair.sites ?? "UNKNOWN"} import sites between the modules of the two groups; Core ${pair.status}.`,
      }));
      return { nodes, edges, declared: [], frames: [], atlas: true, moduleOverview: true,
        boundaryEdges: 0, grouped: { modules: modules.length, limit: MODULE_BOX_LIMIT } };
    }

    function atlasModuleScene(level, viewMode) {
      const modules = atlasModules(level, viewMode), ids = new Set(modules.map((module) => module.id));
      if (modules.length > MODULE_BOX_LIMIT) return groupedModuleScene(level, viewMode, modules);
      const nodes = modules.map((module) => ({
        id: module.id, label: module.path?.split("/").at(-1) || module.name, kind: "module", module,
        entity: null, sourceGraph: null, sections: [], outside: false,
        meta: module.path ? shortPath(module.path) : "File path not declared", tooltip: module.path || module.name,
      }));
      const allDeclared = ATLAS.declared_modules.flatMap((module) =>
        (module.relationships || []).map((edge) => ({ ...edge, source_id: module.id })));
      const declared = allDeclared.filter((edge) => ids.has(edge.source_id) && ids.has(edge.target_id));
      const edges = viewMode === "target" ? declared.map((edge) => ({ ...edge,
        source: edge.source_id, target: edge.target_id, relationshipKind: edge.kind, state: "declared", declaration: edge,
        tooltip: `${edge.kind}: ${edge.id}. ${edge.reason || "Authored module relationship"}`, label: edge.kind,
      })) : level.cells.filter((index) => ids.has(ATLAS.cells[index].source_id) && ids.has(ATLAS.cells[index].target_id))
        .map((index) => { const cell = ATLAS.cells[index]; return { ...cell, id: `module-cell:${index}`, cell: index,
          source: cell.source_id, target: cell.target_id, kind: "dependency", relationshipKind: "imports",
          state: cell.status === "FAIL" ? "violation" : cell.status === "UNKNOWN" ? "undecided" : "observed", label: countLabel(cell.import_sites, "import"),
          tooltip: `${cell.import_sites ?? "UNKNOWN"} import sites; Core ${cell.status}; permission ${cell.permission}.`,
        }; });
      const boundaryEdges = viewMode === "target"
        ? new Set(allDeclared.filter((edge) => ids.has(edge.source_id) !== ids.has(edge.target_id))
          .map((edge) => edge.id)).size
        : new Set(ATLAS.cells.filter((cell) => ids.has(cell.source_id) !== ids.has(cell.target_id))
          .map((cell) => `${cell.source_id}\0${cell.target_id}`)).size;
      return { nodes, edges, declared, frames: [], atlas: true, moduleOverview: true, boundaryEdges };
    }

    function atlasScene(level, viewMode) {
      const children = ATLAS.components.filter((component) => component.parent_id === level.parent_id);
      const ids = new Set(children.map((component) => component.id));
      const declared = children.flatMap((component) => component.requires
        .filter((edge) => ids.has(edge.target_id)).map((edge) => ({ ...edge, source_id: component.id })));
      const nodes = children.map((component) => ({
        id: component.id, label: component.label, kind: component.directory ? "package" : "component",
        entity: null, sourceGraph: null,
        meta: component.responsibilities.join(" ").slice(0, 126) || "Not declared",
        sections: [], outside: false, component,
        tooltip: `${component.label}: ${component.responsibilities.join(" ")}.${viewMode === "target" ? "" : ` ${component.reason}`}`,
      }));
      const declaredEdges = declared.map((edge) => ({
        id: edge.id, source: edge.source_id, target: edge.target_id,
        layoutId: `declared:${edge.id}`,
        kind: "dependency", relationshipKind: "requires", state: "declared", declaration: edge,
        tooltip: edge.rationale, label: "requires",
      }));
      const pairKey = (source, target) => `${source}\0${target}`;
      const permitted = new Set(declared.map((edge) => pairKey(edge.source_id, edge.target_id)));
      const observedEdges = level.edges.map((edge) => {
        const undeclared = deviationIndex.isUndeclared(level.parent_id, edge.source_id, edge.target_id);
        const allowed = permitted.has(pairKey(edge.source_id, edge.target_id));
        const isDiff = viewMode === "diff";
        const edgeId = edge.interface_id !== undefined ? `interface:${edge.interface_id}`
          : `observed:${edge.source_id}>${edge.target_id}`;
        return ({
        ...edge, id: edgeId, layoutId: edgeId,
        source: edge.source_id, target: edge.target_id, kind: "dependency", relationshipKind: "imports",
        // AD-606: in Diff an edge that a failing rule cites is red as an undeclared edge is.
        state: isDiff ? undeclared || edge.status === "FAIL" ? "violation" : edge.status === "UNKNOWN" ? "undecided" : "observed"
          : edge.status === "FAIL" ? "violation" : edge.status === "UNKNOWN" ? "undecided" : "observed",
        edgeClass: isDiff ? undeclared || edge.status === "FAIL" ? "atlas-undeclared" : allowed ? "atlas-permitted" : "atlas-observed" : "",
        // A crossing between two parts of a system is no import: its title names it.
        tooltip: edge.crossing ? `${edge.crossing}. Schema: ${edge.schema}. Interface not checked.`
          : `Observed imports: ${edge.import_sites ?? "UNKNOWN"}. Core ${edge.status}; ${undeclared ? "recorded as undeclared." : allowed ? "declared dependency in use." : "no deviation recorded."}`,
        label: edge.crossing || countLabel(edge.import_sites, "import"),
      });
      });
      const unused = deviationIndex.unused(level.parent_id).map((row) => {
        const source = row.source_id, target = row.target_id;
        const declaration = declaredEdges.find((edge) => edge.source === source && edge.target === target);
        return {
          ...(declaration || { id: `unused:${source}>${target}`,
            layoutId: `declared:unused:${source}>${target}`, source, target,
            kind: "dependency", relationshipKind: "requires" }),
          state: "declared", edgeClass: "atlas-allowed-unused", unused: true, label: "allowed · unused",
          tooltip: declaration?.tooltip || "Allowed dependency with no observed use.",
        };
      });
      const edges = viewMode === "target" ? declaredEdges : viewMode === "diff" ? [...observedEdges, ...unused] : observedEdges;
      const layoutEdges = [...new Map(
        [...unused, ...observedEdges, ...declaredEdges].map((edge) => [edge.layoutId, edge]),
      ).values()];
      return { nodes, edges, layoutEdges, frames: [], componentOverview: true, atlas: true, declared };
    }
    function searchIndex(viewMode) {
      if (!ATLAS) return [];
      const path = (item) => componentRoute(item.id).map((parent) => parent.label).join(" / ");
      const modules = viewMode === "target" ? ATLAS.declared_modules : ATLAS.modules;
      return [
        ...ATLAS.components.map((item) => ({ kind: "component", id: item.id, label: item.label,
          sub: [path(item), item.layer].filter(Boolean).join(" · "), status: item.status,
          text: `${item.label} ${item.path || ""} ${item.id} ${path(item)}`.toLowerCase() })),
        ...modules.map((item) => ({ kind: "module", id: item.id, label: item.name.split(".").at(-1),
          sub: item.path || item.name, text: `${item.name} ${item.path || ""}`.toLowerCase(), module: item })),
        ...ATLAS.rule_assessments.map((item) => ({ kind: "rule", id: item.id, label: item.id,
          sub: `${item.kind} · ${item.scope}`, status: item.status,
          text: `${item.id} ${item.kind} ${item.scope}`.toLowerCase(), rule: item })),
      ];
    }
    return {
      atlas: ATLAS,
      boundaryPermissions,
      searchIndex,
      atlasComponent,
      atlasModuleById,
      entities: nativeGraph.entities,
      entity: nativeGraph.entity,
      parent: nativeGraph.parent,
      label: nativeGraph.label,
      member: nativeGraph.member,
      hasInterior: nativeGraph.hasInterior,
      assessments: nativeGraph.assessments,
      projectArchitectureScene: nativeGraph.projectArchitectureScene,
      unassignedModules: nativeGraph.unassignedModules,
      componentRoute,
      atlasModules,
      atlasModuleScene,
      atlasScene,
      countLabel,
    };
  }
  // Issue 1644: a box that the report makes (a group or a directory) is no decision of the contract.
  const decider = (value) => value === "agent" ? "Agent" : value === "architect" ? "Architect"
    : value === "report" ? "Report (structure)"
    : value && value !== "UNKNOWN" ? String(value) : "Not recorded";
  const perspectives = {
    decision: { label: "Decided by", value: (node) => node.component ? decider(node.component.decided_by) : null,
      colors: { Agent: "var(--accent)", Architect: "var(--ink-muted)", "Report (structure)": "var(--ink-subtle)", "Not recorded": "var(--ink-subtle)" } },
    layer: { label: "Layer", value: (node) => node.component?.layer || null },
    // AD-606: the language of the collector of the modules inside the component, from the frame.
    // A module box carries the language of its own collector, or of its part (issue 1488 review).
    language: { label: "Language", value: (node) => node.component?.language || node.module?.language || null },
    evidence: { label: "Evidence", value: (node) => node.component?.status || null,
      colors: { PASS: "var(--pass)", FAIL: "var(--fail)", UNKNOWN: "var(--unknown)" } },
  };
  const compare = (a, b) => a < b ? -1 : a > b ? 1 : 0;
  function search(index, text, visibleIds = [], limit = 40) {
    const needle = text.trim().toLowerCase();
    const visible = new Set(visibleIds);
    const order = { component: 0, module: 1, rule: 2, element: 3 };
    return index.map((row) => {
      const label = row.label.toLowerCase();
      const score = !needle ? visible.has(row.id) ? 0 : null
        : label === needle ? 0 : label.startsWith(needle) ? 1
          : row.text.split(/[\s./:_-]+/).some((token) => token.startsWith(needle)) ? 2
            : row.text.includes(needle) ? 3 : null;
      return { row, score };
    }).filter((hit) => hit.score !== null)
      .sort((a, b) => a.score - b.score || order[a.row.kind] - order[b.row.kind]
        || compare(a.row.label, b.row.label) || compare(a.row.id, b.row.id))
      .slice(0, limit).map((hit) => hit.row);
  }
  function sceneToMermaid(scene) {
    if (!scene) return "";
    const nodes = [...scene.nodes].sort((a, b) => compare(a.id, b.id));
    const ids = new Map(nodes.map((node, i) => [node.id, `n${i}`]));
    // Mermaid's decimal entities keep user labels out of its grammar and HTML.
    const escape = (value) => String(value ?? "").replace(/[&#"<>|\[\]{}\\\r\n]/g,
      (char) => `#${char.codePointAt(0)};`);
    return ["flowchart LR",
      ...nodes.map((node) => {
        const statuses = [...new Set([node.component?.status,
          ...(node.assessments || []).map((item) => item.status)])];
        return `  ${ids.get(node.id)}["${escape([node.label, ...statuses].filter(Boolean).join(" · "))}"]`;
      }),
      ...[...scene.edges].sort((a, b) => compare(a.id, b.id))
        .filter((edge) => ids.has(edge.source) && ids.has(edge.target))
        .map((edge) => {
          const label = escape([...new Set([edge.label, edge.relationshipKind, edge.resolution,
            edge.status, ...(edge.assessments || []).map((item) => item.status),
            ...(edge.findings || []).map((item) => item.status), edge.state])].filter(Boolean).join(" · "));
          return `  ${ids.get(edge.source)} -->${label ? `|"${label}"|` : ""} ${ids.get(edge.target)}`;
        }),
    ].join("\n");
  }
  /**
   * The chip text of a box for the deviations inside it: the words follow the status of the box. An
   * undeclared dependency is a violation only in a FAIL box; in an UNKNOWN box the run has not decided
   * it; an allowed but unused dependency is no violation in any box.
   * @param {string} status @param {readonly {kind: string}[]} rows @returns {string}
   */
  function deviationChipText(status, rows) {
    const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
    const unused = rows.filter((row) => row.kind === "allowed_unused").length;
    const undeclared = rows.length - unused;
    const parts = [];
    if (undeclared) {
      parts.push(status === "FAIL" ? plural(undeclared, "violation", "violations")
        : status === "UNKNOWN" ? plural(undeclared, "open gap", "open gaps")
          : plural(undeclared, "undeclared dependency", "undeclared dependencies"));
    }
    if (unused) parts.push(plural(unused, "unused permission", "unused permissions"));
    return parts.length ? `${parts.join(" · ")} inside` : "";
  }
  global.ArchkeelReportScene = { create, search, sceneToMermaid, decider, perspectives, deviationChipText };
})(window);
