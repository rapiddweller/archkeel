"use strict";
(function (global) {
  function create(data) {
    const nativeGraph = ArchkeelGraphScene.create(data);
    const ATLAS = data.atlas ? structuredClone(data.atlas) : null;
    const deviationIndex = ATLAS ? ArchkeelAtlasDeviations.create(ATLAS.deviations || []) : null;
    const DATA = { ...data, atlas: ATLAS };
    const NAV = DATA.navigation || null;
    const countLabel = (value, singular, plural = `${singular}s`) =>
      value === null || value === undefined ? `UNKNOWN ${plural}` : `${value} ${value === 1 ? singular : plural}`;
    if (ATLAS) {
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
      ATLAS.assignments = ATLAS.assignments.map(([module, owner, candidates, status, reason]) => ({
        id: ATLAS.modules[module].id, component_id: owner === null ? null : ATLAS.reference_ids[owner],
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

    function atlasModuleScene(level, viewMode) {
      const modules = atlasModules(level, viewMode), ids = new Set(modules.map((module) => module.id));
      const nodes = modules.map((module) => ({
        id: module.id, label: module.path?.split("/").at(-1) || module.name, kind: "module", module,
        entity: null, sourceGraph: null, sections: [], outside: false,
        meta: module.path || "File path not declared", tooltip: module.name,
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
        id: component.id, label: component.label, kind: "component",
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
        return ({
        ...edge, id: `observed:${edge.source_id}>${edge.target_id}`,
        layoutId: `observed:${edge.source_id}>${edge.target_id}`,
        source: edge.source_id, target: edge.target_id, kind: "dependency", relationshipKind: "imports",
        state: isDiff ? undeclared ? "violation" : edge.status === "UNKNOWN" ? "undecided" : "observed"
          : edge.status === "FAIL" ? "violation" : edge.status === "UNKNOWN" ? "undecided" : "observed",
        edgeClass: isDiff ? undeclared ? "atlas-undeclared" : allowed ? "atlas-permitted" : "atlas-observed" : "",
        tooltip: `Observed imports: ${edge.import_sites ?? "UNKNOWN"}. Core ${edge.status}; ${undeclared ? "recorded as undeclared." : allowed ? "declared dependency in use." : "no deviation recorded."}`,
        label: countLabel(edge.import_sites, "import"),
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
  const decider = (value) => value === "agent" ? "Agent" : value === "architect" ? "Architect"
    : value && value !== "UNKNOWN" ? String(value) : "Not recorded";
  const perspectives = {
    decision: { label: "Decided by", value: (node) => node.component ? decider(node.component.decided_by) : null,
      colors: { Agent: "#e8590c", Architect: "#2563eb", "Not recorded": "#868e96" } },
    layer: { label: "Layer", value: (node) => node.component?.layer || null },
    evidence: { label: "Evidence", value: (node) => node.component?.status || null,
      colors: { PASS: "var(--ck-pass)", FAIL: "var(--ck-fail)", UNKNOWN: "var(--ck-unknown)" } },
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
  global.ArchkeelReportScene = { create, search, sceneToMermaid, decider, perspectives };
})(window);
