"use strict";
(function (global) {
  function create(data) {
    const ATLAS = data.atlas ? structuredClone(data.atlas) : null;
    const DATA = { ...data, atlas: ATLAS };
    const NAV = DATA.navigation || null;
    const graphIndexes = new WeakMap();
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
    function architectureEntities(graph) {
      if (graphIndexes.has(graph)) return graphIndexes.get(graph).entities;
      const entities = buildArchitectureEntities(graph);
      const parents = new Map(), children = new Map();
      graphIndexes.set(graph, { entities, byId: new Map(entities.map((entity) => [entity.id, entity])), parents, children });
      for (const entity of entities) {
        const parent = architectureParent(entity, graph);
        parents.set(entity.id, parent);
        if (!children.has(parent)) children.set(parent, []);
        children.get(parent).push(entity);
      }
      return entities;
    }

    function buildArchitectureEntities(graph) {
      if (graph.origin !== "observed" || !DATA.target?.component_intents.length) return graph.entities;
      const unassigned = unassignedArchitectureModules();
      return [...graph.entities.filter((item) => item.kind !== "package" || unassigned.some((module) =>
        module.qualified_name === item.qualified_name || module.qualified_name.startsWith(item.qualified_name + "."))),
        ...DATA.target.entities.filter((item) => item.kind === "component")];
    }

    function architectureEntity(id, graph) {
      architectureEntities(graph);
      return graphIndexes.get(graph).byId.get(id);
    }

    function componentDepth(id) {
      const intent = DATA.target.component_intents.find((item) => item.component_id === id);
      return intent?.parent_id ? 1 + componentDepth(intent.parent_id) : 0;
    }

    function architectureHasInterior(entity, graph, viewMode) {
      architectureEntities(graph);
      if (DATA.observed) architectureEntities(DATA.observed);
      return graphIndexes.get(graph).children.has(entity.id)
        || viewMode === "diff" && graph.origin === "declared" && DATA.observed
          && graphIndexes.get(DATA.observed).children.has(entity.id)
        || graph.relationships.some((site) => site.source_id === entity.id && site.kind !== "owns");
    }

    function architectureParent(entity, graph) {
      const parents = graphIndexes.get(graph)?.parents;
      if (parents?.has(entity.id)) return parents.get(entity.id);
      if (entity.kind === "component") return (graph.origin === "observed" ? DATA.target : graph).component_intents
        .find((item) => item.component_id === entity.id)?.parent_id ?? entity.parent_id;
      if (graph.origin === "observed" && entity.kind === "module") {
        const memberships = (DATA.memberships || []).filter((item) => item.module_ids.includes(entity.id))
          .sort((left, right) => componentDepth(right.component_id) - componentDepth(left.component_id));
        const deepest = memberships.filter((item) => componentDepth(item.component_id)
          === componentDepth(memberships[0]?.component_id));
        if (deepest.length === 1) return deepest[0].component_id;
      }
      if (graph.origin === "observed" && entity.kind === "package") {
        // Namespace nesting is navigation, not a new lexical containment claim.
        const prefix = entity.qualified_name.split(".").slice(0, -1).join(".");
        return graph.entities.find((item) => item.kind === "package" && item.qualified_name === prefix)?.id ?? null;
      }
      return entity.parent_id;
    }

    function architectureLabel(entity, graph) {
      if (entity.kind === "module" && entity.file_path) {
        const filename = entity.file_path.split("/").at(-1);
        if (filename !== "__init__.py") return filename.replace(/\.[^.]+$/, "");
      }
      return (graph.origin === "observed" ? DATA.target?.component_intents || [] : graph.component_intents)
        .find((item) => item.component_id === entity.id)?.label
        || entity.qualified_name.split(".").at(-1);
    }

    function umlMember(entity, includeName = true) {
      const visibility = { public: "+", private: "−", protected: "#", package: "~", unknown: "?" };
      const name = entity.qualified_name.split(".").at(-1);
      if (entity.kind === "enum_literal") return name;
      let text = `${visibility[entity.visibility.kind]} ${includeName ? name : ""}`;
      if (entity.signature) {
        const parameters = [];
        let keywordSeparator = false;
        entity.signature.parameters.forEach((parameter, index, all) => {
          if (parameter.kind === "keyword_only" && !keywordSeparator) {
            parameters.push("*");
            keywordSeparator = true;
          }
          if (parameter.kind === "varargs") keywordSeparator = true;
          const prefix = parameter.kind === "varargs" ? "*" : parameter.kind === "kwargs" ? "**" : "";
          parameters.push(prefix + parameter.name + (parameter.annotation ? `: ${parameter.annotation}` : "")
            + (parameter.default_known && parameter.default !== null ? ` = ${parameter.default}` : ""));
          if (parameter.kind === "positional_only" && all[index + 1]?.kind !== "positional_only") parameters.push("/");
        });
        text += `(${parameters.join(", ")}): ${entity.signature.returns || "?"}`;
      } else if (entity.annotation) text += `: ${entity.annotation}`;
      if (entity.initializer !== null && entity.initializer !== undefined) text += ` = ${entity.initializer}`;
      return text;
    }

    function architectureAssessments(context, id) {
      if (!context.comparison) return [];
      const subjects = new Set([id]);
      for (const entity of context.graph.entities) {
        let parent = architectureParent(entity, context.graph);
        while (parent) {
          if (parent === id) { subjects.add(entity.id); break; }
          const owner = context.graph.entities.find((item) => item.id === parent);
          parent = owner ? architectureParent(owner, context.graph) : null;
        }
      }
      context.graph.relationships.forEach((edge) => {
        if (subjects.has(edge.source_id)) subjects.add(edge.id);
      });
      return context.comparison.assessments.filter((item) => context.graph.origin === "observed"
        ? item.observed_ids.some((id) => subjects.has(id)) : subjects.has(item.subject_id));
    }

    function projectArchitectureScene(context, { viewMode, directChildren = false } = {}) {
      const { graph, scope } = context;
      const displayEntities = architectureEntities(graph);
      const byId = new Map(displayEntities.map((entity) => [entity.id, entity]));
      const componentOverview = scope === null && displayEntities.some((entity) =>
        entity.kind === "component" && architectureParent(entity, graph) === null);
      const local = displayEntities.filter((entity) => architectureParent(entity, graph) === scope
        && entity.presence !== "referenced" && (!componentOverview || entity.kind === "component"));
      const visible = new Map(local.map((entity) => [entity.id, entity]));
      const localIds = new Set(visible.keys());
      const operationScope = ["method", "function"].includes(byId.get(scope)?.kind);
      const coarse = scope === null || byId.get(scope)?.kind === "component";
      const representative = (id) => {
        if (operationScope) return id;
        let current = id;
        let classifier = null;
        let module = null;
        let component = null;
        while (byId.has(current)) {
          if (localIds.has(current)) return current;
          if (current === scope) return current === id && byId.get(current).kind !== "component" ? current : null;
          const entity = byId.get(current);
          if (!classifier && ["class", "interface", "enum", "mixin"].includes(entity.kind)) classifier = current;
          if (!module && entity.kind === "module") module = current;
          if (coarse && !component && entity.kind === "component") component = current;
          current = architectureParent(entity, graph);
        }
        return component || classifier || module || id;
      };
      const observed = viewMode === "diff" && graph.origin === "declared" ? DATA.observed : null;
      const observedById = new Map((observed ? architectureEntities(observed) : []).map((entity) => [entity.id, entity]));
      const counterparts = new Map();
      const observedByTarget = new Map();
      for (const match of context.comparison?.correspondences || []) {
        if (match.observed_ids.length !== 1 || !byId.has(match.target_id)
            || !observedById.has(match.observed_ids[0])) continue;
        const id = match.observed_ids[0];
        if (!counterparts.has(id)) counterparts.set(id, new Set());
        counterparts.get(id).add(match.target_id);
        if (!observedByTarget.has(match.target_id)) observedByTarget.set(match.target_id, new Set());
        observedByTarget.get(match.target_id).add(id);
      }
      const uniqueObservedCounterpart = (id) => {
        const observedIds = observedByTarget.get(id);
        if (observedIds?.size !== 1) return null;
        const [observedId] = observedIds;
        return counterparts.get(observedId)?.size === 1
          ? observedById.get(observedId) || null : null;
      };
      const targetEntry = (id) => ({ id, entity: byId.get(id), sourceGraph: graph,
        local: localIds.has(id) || id === scope });
      const observedEntry = (id, local = false) => ({ id: `observed:${id}`,
        entity: observedById.get(id), sourceGraph: observed, local });
      const observedRepresentative = (id) => {
        let current = id, child = id, classifier = null, module = null;
        while (observedById.has(current)) {
          if (current === scope) return observedEntry(classifier || child, true);
          if (byId.get(current)?.kind === "component") return targetEntry(representative(current));
          const mapped = [...new Set([...(counterparts.get(current) || [])]
            .map(representative).filter(Boolean))];
          const local = mapped.filter((id) => localIds.has(id));
          const choices = local.length ? local : mapped;
          if (choices.length === 1) {
            if (operationScope && current !== id) {
              return observedEntry(id, choices[0] === scope || localIds.has(choices[0]));
            }
            if (choices[0] === scope && current !== id) return observedEntry(classifier || child, true);
            return targetEntry(choices[0]);
          }
          if (observedLocalIds.has(current)) return observedEntry(current, true);
          const entity = observedById.get(current);
          if (!classifier && ["class", "interface", "enum", "mixin"].includes(entity.kind)) classifier = current;
          if (!module && entity.kind === "module") module = current;
          child = current;
          current = architectureParent(entity, observed);
        }
        return observedEntry(operationScope ? id : classifier || module || id, scope === null);
      };
      const entries = new Map([...visible].map(([id]) => [id, targetEntry(id)]));
      const observedLocalIds = new Set((observed ? architectureEntities(observed) : []).filter((entity) =>
        ["package", "module"].includes(entity.kind) && entity.presence !== "referenced"
        && architectureParent(entity, observed) === scope).map((entity) => entity.id));
      for (const id of observedLocalIds) {
        if (componentOverview || context.comparison && scope !== null) continue;
        const entry = observedRepresentative(id);
        if (entry.entity && entry.local) entries.set(entry.id, entry);
      }
      const groups = new Map();
      const unassignedIds = new Set(componentOverview
        ? unassignedArchitectureModules().map((entity) => entity.id) : []);
      const addSite = (site, source, target, sourceGraph, assessment = null) => {
        if (!source?.entity || !target?.entity || (!source.local && !target.local)) return;
        if (directChildren && (!localIds.has(site.source_id) || !localIds.has(target.entity.id)
            || site.target_id !== target.entity.id && !site.candidate_ids.includes(target.entity.id))) return;
        if (componentOverview && [source, target].some((entry) => entry.entity.kind !== "component")
            && !(sourceGraph.origin === "observed" && site.kind === "imports"
              && [source, target].every((entry) => entry.entity.kind === "component"
                || unassignedIds.has(entry.entity.id)))) return;
        if (source.id === target.id && site.source_id !== site.target_id) return;
        for (const entry of [source, target]) if (!entries.has(entry.id)) entries.set(entry.id, entry);
        const id = site.kind === "requires" ? site.id
          : `${sourceGraph !== graph ? "observed:" : ""}${site.kind}:${source.id}>${target.id}:${site.resolution}`;
        if (!groups.has(id)) groups.set(id, { id, source: source.id, target: target.id, kind: "dependency",
          relationshipKind: site.kind, sites: [], sourceGraph, assessments: [], resolution: site.resolution,
          state: assessment?.status === "FAIL" ? "violation" : assessment?.status === "UNKNOWN" ? "undecided"
            : sourceGraph.origin === "declared" ? "declared"
            : site.resolution === "partial" ? "undecided" : "observed" });
        const edge = groups.get(id);
        if (!edge.sites.some((item) => item.id === site.id)) edge.sites.push(site);
        if (assessment && !edge.assessments.some((item) => item.id === assessment.id)) edge.assessments.push(assessment);
      };
      for (const site of graph.relationships) {
        if (site.kind === "owns") continue;
        // Component dependencies use imports; operation sites remain in Details and module drill-down.
        if (coarse && !["imports", "requires"].includes(site.kind)) continue;
        if (coarse
            && byId.get(site.source_id)?.presence === "referenced") continue;
        const source = representative(site.source_id);
        const targets = site.target_id ? [site.target_id] : site.candidate_ids;
        for (const endpoint of targets) {
          if (coarse
              && byId.get(endpoint)?.presence === "referenced") continue;
          const target = representative(endpoint);
          addSite(site, targetEntry(source), targetEntry(target), graph);
        }
      }
      const unexpected = (context.comparison?.assessments || []).filter((item) => item.change === "unexpected");
      const observedSites = new Map((observed?.relationships || []).map((site) => [site.id, site]));
      const representedSites = new Set((context.comparison?.assessments || [])
        .filter((match) => graph.relationships.some((site) => site.id === match.subject_id))
        .flatMap((match) => match.observed_ids));
      for (const site of observedSites.values()) {
        const assessment = unexpected.find((item) => item.observed_ids.includes(site.id));
        if (representedSites.has(site.id) || (!assessment && site.kind !== "imports")) continue;
        if (coarse && site.kind !== "imports") continue;
        for (const endpoint of new Set(site.target_id ? [site.target_id] : site.candidate_ids)) {
          addSite(site, observedRepresentative(site.source_id), observedRepresentative(endpoint), observed, assessment);
        }
      }
      for (const assessment of unexpected) for (const id of assessment.observed_ids) {
        const entity = observedById.get(id);
        if (entity && assessment.subject_id === scope) entries.set(`observed:${id}`, observedEntry(id, true));
      }
      const nodes = [...entries.values()].map(({ id, entity, sourceGraph, local }) => {
        const children = graphIndexes.get(sourceGraph).children.get(entity.id) || [];
        const observedCounterpart = viewMode === "diff" && sourceGraph === graph
          && graph.origin === "declared" ? uniqueObservedCounterpart(entity.id) : null;
        const boundary = (sourceGraph.origin === "observed" ? DATA.target?.component_intents || [] : sourceGraph.component_intents)
          .find((item) => item.component_id === entity.id);
        const assessments = sourceGraph === graph ? architectureAssessments(context, entity.id)
          : unexpected.filter((item) => item.observed_ids.includes(entity.id));
        for (const edge of groups.values()) if (edge.source === id) {
          for (const item of edge.assessments) if (!assessments.some((found) => found.id === item.id)) assessments.push(item);
        }
        const fields = children.filter((child) => child.kind === "attribute");
        const literals = children.filter((child) => child.kind === "enum_literal");
        const methods = children.filter((child) => child.kind === "method");
        const sections = [
          ["Literals", literals], ["Attributes", fields], ["Operations", methods],
        ].filter(([, entries]) => entries.length).map(([label, entries]) => ({ label,
          lines: [...entries.slice(0, 3).map((entry) => ({ text: umlMember(entry),
            static: entry.modifiers.includes("static") })),
            ...(entries.length > 3 ? [{ text: `… ${entries.length - 3} more · Open selected`, static: false }] : [])] }));
        const meta = entity.kind === "enum_literal" ? ""
          : ["method", "function", "attribute", "binding"].includes(entity.kind)
          ? umlMember(entity, !["method", "function"].includes(entity.kind))
          : entity.presence === "referenced" ? "Referenced symbol"
          : entity.kind === "component" ? `Architecture boundary${boundary?.role && boundary.role !== "component" ? ` · Role: ${boundary.role}` : ""} · ${children.length} inner element${children.length === 1 ? "" : "s"}`
          : entity.kind === "package" ? `Namespace group${sourceGraph !== graph ? " · observed" : ""} · ${children.length} inner element${children.length === 1 ? "" : "s"}`
          : entity.kind === "module" ? `${sourceGraph !== graph ? "Observed · " : ""}${entity.file_path?.split("/").at(-1) || "File not declared"} · ${children.length} inner element${children.length === 1 ? "" : "s"}`
          : sourceGraph !== graph ? `Observed · ${unexpected.some((item) => item.observed_ids.includes(entity.id)) ? "unlisted definition" : "relationship endpoint"}`
          : `${children.length} inner element${children.length === 1 ? "" : "s"}`;
        return { id, kind: entity.kind, entity, sourceGraph, assessments,
          observedCounterpart,
          label: architectureLabel(entity, sourceGraph),
          meta: observedCounterpart?.kind === "binding"
            ? `${meta} · As-Is: ${umlMember(observedCounterpart)}` : meta,
          sections, memberCounts: { literals: literals.length, fields: fields.length, methods: methods.length }, outside: !local,
          tooltip: `${entity.kind}: ${entity.qualified_name}. ${entity.presence}. ${entity.responsibilities.join(" ")}` };
      });
      const edges = [...groups.values()].map((edge) => {
        const assessments = [...new Map([...edge.assessments, ...(context.comparison?.assessments.filter((item) =>
          edge.sites.some((site) => edge.sourceGraph.origin === "observed"
            ? item.observed_ids.includes(site.id) : site.id === item.subject_id)) || [])]
          .map((item) => [item.id, item])).values()];
        const observedSites = [...new Set((context.comparison?.assessments || [])
          .filter((match) => edge.sites.some((site) => site.id === match.subject_id))
          .flatMap((match) => match.observed_ids))].map((id) => DATA.observed?.relationships.find((site) => site.id === id)).filter(Boolean);
        const findings = (viewMode === "target" ? [] : DATA.findings || []).filter((item) => [...edge.sites, ...observedSites]
          .some((site) => item.graph_subject_ids.includes(site.id)));
        const statuses = [...new Set([...assessments, ...findings].map((item) => item.status))];
        const decisionGaps = (DATA.decision_gaps || []).filter((gap) => edge.sourceGraph.origin === "observed"
          && edge.sites.some((site) => gap.relationship_ids.includes(site.id)));
        return { ...edge, observedSites, assessments, findings, decisionGaps,
          state: statuses.includes("FAIL") ? "violation" : statuses.includes("UNKNOWN") || decisionGaps.length ? "undecided" : edge.state,
          tooltip: `${edge.relationshipKind === "requires" ? "Allowed component import" : edge.relationshipKind}${edge.resolution === "partial" ? " candidate; not confirmed" : ""}: ${
            edge.sourceGraph.entities.find((item) => item.id === edge.sites[0].source_id).qualified_name} → ${
            edge.sourceGraph.entities.find((item) => item.id === (edge.sites[0].target_id || edge.sites[0].candidate_ids[0])).qualified_name}; ${
            edge.sites.length + observedSites.length} source or declaration site${edge.sites.length + observedSites.length === 1 ? "" : "s"}.${statuses.length ? ` Core ${statuses.join("/")}${assessments.some((item) => item.change === "unexpected") ? " · unlisted observed relationship" : ""}.` : ""}`,
        };
      });
      return { nodes, frames: [], edges, owner: scope, componentOverview };
    }

    function unassignedArchitectureModules() {
      const components = new Set((DATA.target?.component_intents || []).map((item) => item.component_id));
      return (DATA.observed?.entities || []).filter((item) => item.kind === "module"
        && item.presence === "defined" && !components.has(architectureParent(item, DATA.observed)))
        .sort((left, right) => (left.file_path || left.qualified_name).localeCompare(right.file_path || right.qualified_name));
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
      const deviations = new Map((ATLAS.deviations || []).filter((item) => item.level_id === level.parent_id)
        .map((item) => [pairKey(item.source_id, item.target_id), item.kind]));
      const permitted = new Set(declared.map((edge) => pairKey(edge.source_id, edge.target_id)));
      const observedEdges = level.edges.map((edge) => {
        const deviation = deviations.get(pairKey(edge.source_id, edge.target_id));
        const allowed = permitted.has(pairKey(edge.source_id, edge.target_id));
        const isDiff = viewMode === "diff";
        return ({
        ...edge, id: `observed:${edge.source_id}>${edge.target_id}`,
        layoutId: `observed:${edge.source_id}>${edge.target_id}`,
        source: edge.source_id, target: edge.target_id, kind: "dependency", relationshipKind: "imports",
        state: isDiff ? deviation === "undeclared" ? "violation" : edge.status === "UNKNOWN" ? "undecided" : "observed"
          : edge.status === "FAIL" ? "violation" : edge.status === "UNKNOWN" ? "undecided" : "observed",
        edgeClass: isDiff ? deviation === "undeclared" ? "atlas-undeclared" : allowed ? "atlas-permitted" : "atlas-observed" : "",
        tooltip: `Observed imports: ${edge.import_sites ?? "UNKNOWN"}. Core ${edge.status}; ${deviation === "undeclared" ? "recorded as undeclared." : allowed ? "declared dependency in use." : "no deviation recorded."}`,
        label: countLabel(edge.import_sites, "import"),
      });
      });
      const unusedPairs = [...deviations].filter(([, kind]) => kind === "allowed_unused").map(([pair]) => pair);
      const unused = unusedPairs.map((pair) => {
        const [source, target] = pair.split("\0");
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
    return {
      atlas: ATLAS,
      atlasComponent,
      atlasModuleById,
      entities: architectureEntities,
      entity: architectureEntity,
      parent: architectureParent,
      label: architectureLabel,
      member: umlMember,
      hasInterior: architectureHasInterior,
      assessments: architectureAssessments,
      projectArchitectureScene,
      unassignedModules: unassignedArchitectureModules,
      componentRoute,
      atlasModules,
      atlasModuleScene,
      atlasScene,
      countLabel,
    };
  }
  global.ArchkeelReportScene = { create };
})(window);
