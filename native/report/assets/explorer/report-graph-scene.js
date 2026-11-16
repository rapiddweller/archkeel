"use strict";
// Native graph projection owns containment, member presentation and scene construction.
/** @typedef {ArchkeelGraphSceneProtocol.Graph} Graph */
/** @typedef {ArchkeelGraphSceneProtocol.Entity} Entity */
/** @typedef {ArchkeelGraphSceneProtocol.Relationship} Relationship */
/** @typedef {ArchkeelGraphSceneProtocol.Assessment} Assessment */
/** @typedef {ArchkeelGraphSceneProtocol.Context} Context */
/** @typedef {ArchkeelGraphSceneProtocol.Options} Options */
/** @typedef {ArchkeelGraphSceneProtocol.Scene} Scene */
/** @typedef {ArchkeelGraphSceneProtocol.Entry} Entry */
/** @typedef {ArchkeelGraphSceneProtocol.EdgeGroup} EdgeGroup */
/** @typedef {ArchkeelGraphSceneProtocol.GraphIndex} GraphIndex */
/** @typedef {ArchkeelGraphSceneProtocol.ViewMode} PView */
var ArchkeelGraphScene = (function () {
  const G = ArchkeelGraphProtocol;
  const P = ArchkeelGraphSceneProtocol;
  const visibility = new Map([
    [G.VisibilityKind.PUBLIC, "+"], [G.VisibilityKind.PRIVATE, "−"],
    [G.VisibilityKind.PROTECTED, "#"], [G.VisibilityKind.PACKAGE, "~"], [G.VisibilityKind.UNKNOWN, "?"],
  ]);
  /** @param {unknown} data */
  function create(data) {
    const DATA = P.decodeReport(data);
    /** @type {WeakMap<Graph, GraphIndex>} */
    const graphIndexes = new WeakMap();
    /** @param {Graph | null | undefined} graph */
    const componentIntents = (graph) => graph?.component_intents || [];
    /** @param {Graph} graph @returns {GraphIndex} */
    function graphIndex(graph) {
      architectureEntities(graph);
      const index = graphIndexes.get(graph);
      if (!index) throw new Error("Scene graph index was not initialized");
      return index;
    }
    /** @param {Graph} graph @param {string | undefined} id @returns {string} */
    function endpointName(graph, id) {
      const entity = graph.entities.find((item) => item.id === id);
      if (!entity) throw new TypeError("Scene relationship endpoint is missing");
      return entity.qualified_name;
    }
    /** @param {Context} context @returns {ArchkeelGraphSceneProtocol.Comparison | null} */
    function comparisonFor(context) {
      const comparison = context.comparison ?? null;
      const index = graphIndex(context.graph);
      if (comparison !== DATA.comparison && comparison !== index.comparison) {
        index.comparison = P.decodeComparison(comparison);
      }
      return comparison;
    }
    /** @param {Graph} graph @returns {Entity[]} */
    function architectureEntities(graph) {
      const existing = graphIndexes.get(graph);
      if (existing) return existing.entities;
      if (graph !== DATA.observed && graph !== DATA.target) P.decodeGraph(graph);
      const entities = buildArchitectureEntities(graph);
      /** @type {Map<string, string | null>} */
      const parents = new Map();
      /** @type {Map<string | null, Entity[]>} */
      const children = new Map();
      graphIndexes.set(graph, { entities, byId: new Map(entities.map((entity) => [entity.id, entity])), parents, children });
      for (const entity of entities) {
        const parent = architectureParent(entity, graph);
        parents.set(entity.id, parent);
        const siblings = children.get(parent) || [];
        siblings.push(entity);
        children.set(parent, siblings);
      }
      return entities;
    }

    /** @param {Graph} graph @returns {Entity[]} */
    function buildArchitectureEntities(graph) {
      const target = DATA.target;
      if (!target || graph.origin !== G.OriginKind.OBSERVED || !componentIntents(target).length) return graph.entities;
      const unassigned = unassignedArchitectureModules();
      return [...graph.entities.filter((item) => item.kind !== G.EntityKind.PACKAGE || unassigned.some((module) =>
        module.qualified_name === item.qualified_name || module.qualified_name.startsWith(item.qualified_name + "."))),
        ...target.entities.filter((item) => item.kind === G.EntityKind.COMPONENT)];
    }

    /** @param {string} id @param {Graph} graph @returns {Entity | undefined} */
    function architectureEntity(id, graph) {
      architectureEntities(graph);
      return graphIndex(graph).byId.get(id);
    }

    /** @param {string | undefined} id @returns {number} */
    function componentDepth(id) {
      const intent = componentIntents(DATA.target).find((item) => item.component_id === id);
      return intent?.parent_id ? 1 + componentDepth(intent.parent_id) : 0;
    }

    /** @param {Entity} entity @param {Graph} graph @param {PView} viewMode @returns {boolean} */
    function architectureHasInterior(entity, graph, viewMode) {
      architectureEntities(graph);
      if (DATA.observed) architectureEntities(DATA.observed);
      return graphIndex(graph).children.has(entity.id)
        || viewMode === P.ViewMode.DIFF && graph.origin === G.OriginKind.DECLARED && Boolean(DATA.observed)
          && DATA.observed !== null && DATA.observed !== undefined && graphIndex(DATA.observed).children.has(entity.id)
        || graph.relationships.some((site) => site.source_id === entity.id && site.kind !== G.RelationshipKind.OWNS);
    }

    /** @param {Entity} entity @param {Graph} graph @returns {string | null} */
    function architectureParent(entity, graph) {
      const parents = graphIndexes.get(graph)?.parents;
      const recordedParent = parents?.get(entity.id);
      if (recordedParent !== undefined) return recordedParent;
      if (entity.kind === G.EntityKind.COMPONENT) return componentIntents(graph.origin === G.OriginKind.OBSERVED ? DATA.target : graph)
        .find((item) => item.component_id === entity.id)?.parent_id ?? entity.parent_id;
      if (graph.origin === G.OriginKind.OBSERVED && entity.kind === G.EntityKind.MODULE) {
        const memberships = (DATA.memberships || []).filter((item) => item.module_ids.includes(entity.id))
          .sort((left, right) => componentDepth(right.component_id) - componentDepth(left.component_id));
        const deepest = memberships.filter((item) => componentDepth(item.component_id)
          === componentDepth(memberships[0]?.component_id));
        if (deepest.length === 1) return deepest[0].component_id;
      }
      if (graph.origin === G.OriginKind.OBSERVED && entity.kind === G.EntityKind.PACKAGE) {
        // Namespace nesting is navigation, not a new lexical containment claim.
        const prefix = entity.qualified_name.split(".").slice(0, -1).join(".");
        return graph.entities.find((item) => item.kind === G.EntityKind.PACKAGE && item.qualified_name === prefix)?.id ?? null;
      }
      return entity.parent_id;
    }

    /** @param {Entity} entity @param {Graph} graph @returns {string} */
    function architectureLabel(entity, graph) {
      if (entity.kind === G.EntityKind.MODULE && entity.file_path) {
        const filename = entity.file_path.split("/").at(-1) || entity.qualified_name;
        if (P.classifyModuleFileName(filename) !== P.ModuleFileKind.PYTHON_INITIALIZER) return filename.replace(/\.[^.]+$/, "");
      }
      return componentIntents(graph.origin === G.OriginKind.OBSERVED ? DATA.target : graph)
        .find((item) => item.component_id === entity.id)?.label
        || entity.qualified_name.split(".").at(-1) || entity.qualified_name;
    }

    /** @param {Entity} entity @param {boolean} includeName @returns {string} */
    function umlMember(entity, includeName = true) {

      const name = entity.qualified_name.split(".").at(-1) || entity.qualified_name;
      if (entity.kind === G.EntityKind.ENUM_LITERAL) return name;
      let text = `${visibility.get(entity.visibility?.kind ?? G.VisibilityKind.UNKNOWN)} ${includeName ? name : ""}`;
      if (entity.signature) {
        /** @type {string[]} */
        const parameters = [];
        let keywordSeparator = false;
        entity.signature.parameters.forEach((parameter, index, all) => {
          if (parameter.kind === G.ParameterKind.KEYWORD_ONLY && !keywordSeparator) {
            parameters.push("*");
            keywordSeparator = true;
          }
          if (parameter.kind === G.ParameterKind.VARARGS) keywordSeparator = true;
          const prefix = parameter.kind === G.ParameterKind.VARARGS ? "*" : parameter.kind === G.ParameterKind.KWARGS ? "**" : "";
          parameters.push(prefix + parameter.name + (parameter.annotation ? `: ${parameter.annotation}` : "")
            + (parameter.default_known && parameter.default !== null ? ` = ${parameter.default}` : ""));
          if (parameter.kind === G.ParameterKind.POSITIONAL_ONLY && all[index + 1]?.kind !== G.ParameterKind.POSITIONAL_ONLY) parameters.push("/");
        });
        text += `(${parameters.join(", ")}): ${entity.signature.returns || "?"}`;
      } else if (entity.annotation) text += `: ${entity.annotation}`;
      if (entity.initializer !== null && entity.initializer !== undefined) text += ` = ${entity.initializer}`;
      return text;
    }

    /** @param {Context} context @param {string} id @returns {Assessment[]} */
    function architectureAssessments(context, id) {
      const comparison = comparisonFor(context);
      if (!comparison) return [];
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
      return comparison.assessments.filter((item) => context.graph.origin === G.OriginKind.OBSERVED
        ? item.observed_ids.some((id) => subjects.has(id)) : subjects.has(item.subject_id));
    }

    /** @param {Context} context @param {Options} [options] @returns {Scene} */
    function projectArchitectureScene(context, options = {}) {
      /** @type {ArchkeelGraphSceneProtocol.ProjectionMode} */
      const viewMode = P.projectViewMode(P.decodeViewMode(options.viewMode === undefined
        ? P.ViewMode.DIAGRAM : options.viewMode));
      const directChildren = options.directChildren ?? false;
      const comparison = comparisonFor(context);
      const { graph, scope } = context;
      const displayEntities = architectureEntities(graph);
      const byId = new Map(displayEntities.map((entity) => [entity.id, entity]));
      const componentOverview = scope === null && displayEntities.some((entity) =>
        entity.kind === G.EntityKind.COMPONENT && architectureParent(entity, graph) === null);
      const local = displayEntities.filter((entity) => architectureParent(entity, graph) === scope
        && entity.presence !== G.PresenceKind.REFERENCED && (!componentOverview || entity.kind === G.EntityKind.COMPONENT));
      const visible = new Map(local.map((entity) => [entity.id, entity]));
      const localIds = new Set(visible.keys());
      const scopeKind = scope === null ? undefined : byId.get(scope)?.kind;
      const operationScope = scopeKind === G.EntityKind.METHOD || scopeKind === G.EntityKind.FUNCTION;
      const coarse = scope === null || (scope === null ? undefined : byId.get(scope))?.kind === G.EntityKind.COMPONENT;
      /** @param {string | null} id @returns {string | null} */
      const representative = (id) => {
        if (operationScope) return id;
        let current = id;
        let classifier = null;
        let module = null;
        let component = null;
        while (current !== null) {
          const entity = byId.get(current);
          if (!entity) break;
          if (localIds.has(current)) return current;
          if (current === scope) return current === id && entity.kind !== G.EntityKind.COMPONENT ? current : null;
          if (!classifier && [G.EntityKind.CLASS, G.EntityKind.INTERFACE, G.EntityKind.ENUM, G.EntityKind.MIXIN].includes(entity.kind)) classifier = current;
          if (!module && entity.kind === G.EntityKind.MODULE) module = current;
          if (coarse && !component && entity.kind === G.EntityKind.COMPONENT) component = current;
          current = architectureParent(entity, graph);
        }
        return component || classifier || module || id;
      };
      const observed = viewMode === P.ViewMode.DIFF && graph.origin === G.OriginKind.DECLARED ? DATA.observed : null;
      const observedById = new Map((observed ? architectureEntities(observed) : []).map((entity) => [entity.id, entity]));
      /** @type {Map<string, Set<string>>} */
      const counterparts = new Map();
      /** @type {Map<string, Set<string>>} */
      const observedByTarget = new Map();
      for (const match of comparison?.correspondences || []) {
        if (match.observed_ids.length !== 1 || !byId.has(match.target_id)
            || !observedById.has(match.observed_ids[0])) continue;
        const id = match.observed_ids[0];
        const targets = counterparts.get(id) || new Set();
        targets.add(match.target_id); counterparts.set(id, targets);
        const observedIds = observedByTarget.get(match.target_id) || new Set();
        observedIds.add(id); observedByTarget.set(match.target_id, observedIds);
      }
      /** @param {string} id @returns {Entity | null} */
      const uniqueObservedCounterpart = (id) => {
        const observedIds = observedByTarget.get(id);
        if (observedIds?.size !== 1) return null;
        const [observedId] = observedIds;
        return counterparts.get(observedId)?.size === 1
          ? observedById.get(observedId) || null : null;
      };
      /** @param {string | null} id @returns {Entry | null} */
      const targetEntry = (id) => {
        const entity = id === null ? undefined : byId.get(id);
        return id !== null && entity ? { id, entity, sourceGraph: graph, local: localIds.has(id) || id === scope } : null;
      };
      /** @param {string} id @param {boolean} local @returns {Entry | null} */
      const observedEntry = (id, local = false) => {
        const entity = observedById.get(id);
        return entity && observed ? { id: `observed:${id}`, entity, sourceGraph: observed, local } : null;
      };
      /** @param {string} id @returns {Entry | null} */
      const observedRepresentative = (id) => {
        if (!observed) return null;
        /** @type {string | null} */
        let current = id;
        let child = id, classifier = null, module = null;
        while (current !== null) {
          const entity = observedById.get(current);
          if (!entity) break;
          if (current === scope) return observedEntry(classifier || child, true);
          if (byId.get(current)?.kind === G.EntityKind.COMPONENT) return targetEntry(representative(current));
          const mapped = [...new Set([...(counterparts.get(current) || [])]
            .map(representative).filter((id) => id !== null))];
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
          if (!classifier && [G.EntityKind.CLASS, G.EntityKind.INTERFACE, G.EntityKind.ENUM, G.EntityKind.MIXIN].includes(entity.kind)) classifier = current;
          if (!module && entity.kind === G.EntityKind.MODULE) module = current;
          child = current;
          current = architectureParent(entity, observed);
        }
        return observedEntry(operationScope ? id : classifier || module || id, scope === null);
      };
      /** @type {Map<string, Entry>} */
      const entries = new Map();
      for (const id of visible.keys()) { const entry = targetEntry(id); if (entry) entries.set(id, entry); }
      const observedLocalIds = new Set((observed ? architectureEntities(observed) : []).filter((entity) =>
        [G.EntityKind.PACKAGE, G.EntityKind.MODULE].includes(entity.kind) && entity.presence !== G.PresenceKind.REFERENCED
        && observed !== null && observed !== undefined && architectureParent(entity, observed) === scope).map((entity) => entity.id));
      for (const id of observedLocalIds) {
        if (componentOverview || comparison && scope !== null) continue;
        const entry = observedRepresentative(id);
        if (entry && entry.local) entries.set(entry.id, entry);
      }
      /** @type {Map<string, EdgeGroup>} */
      const groups = new Map();
      const unassignedIds = new Set(componentOverview
        ? unassignedArchitectureModules().map((entity) => entity.id) : []);
      /** @param {Relationship} site @param {Entry | null} source @param {Entry | null} target @param {Graph | null | undefined} sourceGraph @param {Assessment | null} assessment */
      const addSite = (site, source, target, sourceGraph, assessment = null) => {
        if (!source || !target || !sourceGraph || (!source.local && !target.local)) return;
        if (directChildren && (!localIds.has(site.source_id) || !localIds.has(target.entity.id)
            || site.target_id !== target.entity.id && !site.candidate_ids.includes(target.entity.id))) return;
        if (componentOverview && [source, target].some((entry) => entry.entity.kind !== G.EntityKind.COMPONENT)
            && !(sourceGraph.origin === G.OriginKind.OBSERVED && site.kind === G.RelationshipKind.IMPORTS
              && [source, target].every((entry) => entry.entity.kind === G.EntityKind.COMPONENT
                || unassignedIds.has(entry.entity.id)))) return;
        if (source.id === target.id && site.source_id !== site.target_id) return;
        for (const entry of [source, target]) if (!entries.has(entry.id)) entries.set(entry.id, entry);
        const id = site.kind === G.RelationshipKind.REQUIRES ? site.id
          : `${sourceGraph !== graph ? "observed:" : ""}${site.kind}:${source.id}>${target.id}:${site.resolution}`;
        if (!groups.has(id)) groups.set(id, { id, source: source.id, target: target.id, kind: P.SceneEdgeKind.DEPENDENCY,
          relationshipKind: site.kind, sites: [], sourceGraph, assessments: [], resolution: site.resolution,
          state: assessment?.status === G.AssessmentStatus.FAIL ? P.EdgeState.VIOLATION : assessment?.status === G.AssessmentStatus.UNKNOWN ? P.EdgeState.UNDECIDED
            : sourceGraph.origin === G.OriginKind.DECLARED ? P.EdgeState.DECLARED
            : site.resolution === G.ResolutionKind.PARTIAL ? P.EdgeState.UNDECIDED : P.EdgeState.OBSERVED });
        const edge = groups.get(id);
        if (!edge) throw new Error("Scene edge group was not initialized");
        if (!edge.sites.some((item) => item.id === site.id)) edge.sites.push(site);
        if (assessment && !edge.assessments.some((item) => item.id === assessment.id)) edge.assessments.push(assessment);
      };
      for (const site of graph.relationships) {
        if (site.kind === G.RelationshipKind.OWNS) continue;
        // Component dependencies use imports; operation sites remain in Details and module drill-down.
        if (coarse && ![G.RelationshipKind.IMPORTS, G.RelationshipKind.REQUIRES].includes(site.kind)) continue;
        if (coarse
            && byId.get(site.source_id)?.presence === G.PresenceKind.REFERENCED) continue;
        const source = representative(site.source_id);
        const targets = site.target_id ? [site.target_id] : site.candidate_ids;
        for (const endpoint of targets) {
          if (coarse
              && byId.get(endpoint)?.presence === G.PresenceKind.REFERENCED) continue;
          const target = representative(endpoint);
          addSite(site, targetEntry(source), targetEntry(target), graph);
        }
      }
      const unexpected = (comparison?.assessments || []).filter((item) => item.change === G.AssessmentChange.UNEXPECTED);
      const observedSites = new Map((observed?.relationships || []).map((site) => [site.id, site]));
      const representedSites = new Set((comparison?.assessments || [])
        .filter((match) => graph.relationships.some((site) => site.id === match.subject_id))
        .flatMap((match) => match.observed_ids));
      for (const site of observedSites.values()) {
        const assessment = unexpected.find((item) => item.observed_ids.includes(site.id));
        if (representedSites.has(site.id) || (!assessment && site.kind !== G.RelationshipKind.IMPORTS)) continue;
        if (coarse && site.kind !== G.RelationshipKind.IMPORTS) continue;
        for (const endpoint of new Set(site.target_id ? [site.target_id] : site.candidate_ids)) {
          addSite(site, observedRepresentative(site.source_id), observedRepresentative(endpoint), observed, assessment);
        }
      }
      for (const assessment of unexpected) for (const id of assessment.observed_ids) {
        const entity = observedById.get(id);
        if (entity && assessment.subject_id === scope) {
          const entry = observedEntry(id, true); if (entry) entries.set(entry.id, entry);
        }
      }
      const nodes = [...entries.values()].map(({ id, entity, sourceGraph, local }) => {
        const children = graphIndex(sourceGraph).children.get(entity.id) || [];
        const observedCounterpart = viewMode === P.ViewMode.DIFF && sourceGraph === graph
          && graph.origin === G.OriginKind.DECLARED ? uniqueObservedCounterpart(entity.id) : null;
        const boundary = componentIntents(sourceGraph.origin === G.OriginKind.OBSERVED ? DATA.target : sourceGraph)
          .find((item) => item.component_id === entity.id);
        const assessments = sourceGraph === graph ? architectureAssessments(context, entity.id)
          : unexpected.filter((item) => item.observed_ids.includes(entity.id));
        for (const edge of groups.values()) if (edge.source === id) {
          for (const item of edge.assessments) if (!assessments.some((found) => found.id === item.id)) assessments.push(item);
        }
        const fields = children.filter((child) => child.kind === G.EntityKind.ATTRIBUTE);
        const literals = children.filter((child) => child.kind === G.EntityKind.ENUM_LITERAL);
        const methods = children.filter((child) => child.kind === G.EntityKind.METHOD);
        /** @type {[string, Entity[]][]} */
        const memberGroups = [
          ["Literals", literals], ["Attributes", fields], ["Operations", methods],
        ];
        const sections = memberGroups.filter(([, entries]) => entries.length).map(([label, entries]) => ({ label,
          lines: [...entries.slice(0, 3).map((entry) => ({ text: umlMember(entry),
            static: entry.modifiers.includes(G.ModifierKind.STATIC) })),
            ...(entries.length > 3 ? [{ text: `… ${entries.length - 3} more · Open selected`, static: false }] : [])] }));
        const meta = entity.kind === G.EntityKind.ENUM_LITERAL ? ""
          : [G.EntityKind.METHOD, G.EntityKind.FUNCTION, G.EntityKind.ATTRIBUTE, G.EntityKind.BINDING].includes(entity.kind)
          ? umlMember(entity, ![G.EntityKind.METHOD, G.EntityKind.FUNCTION].includes(entity.kind))
          : entity.presence === G.PresenceKind.REFERENCED ? "Referenced symbol"
          : entity.kind === G.EntityKind.COMPONENT ? `Architecture boundary${boundary?.role && boundary.role !== G.ComponentRole.COMPONENT ? ` · Role: ${boundary.role}` : ""} · ${children.length} inner element${children.length === 1 ? "" : "s"}`
          : entity.kind === G.EntityKind.PACKAGE ? `Namespace group${sourceGraph !== graph ? " · observed" : ""} · ${children.length} inner element${children.length === 1 ? "" : "s"}`
          : entity.kind === G.EntityKind.MODULE ? `${sourceGraph !== graph ? "Observed · " : ""}${entity.file_path?.split("/").at(-1) || "File not declared"} · ${children.length} inner element${children.length === 1 ? "" : "s"}`
          : sourceGraph !== graph ? `Observed · ${unexpected.some((item) => item.observed_ids.includes(entity.id)) ? "unlisted definition" : "relationship endpoint"}`
          : `${children.length} inner element${children.length === 1 ? "" : "s"}`;
        return { id, kind: entity.kind, entity, sourceGraph, assessments,
          observedCounterpart,
          label: architectureLabel(entity, sourceGraph),
          meta: observedCounterpart?.kind === G.EntityKind.BINDING
            ? `${meta} · As-Is: ${umlMember(observedCounterpart)}` : meta,
          sections, memberCounts: { literals: literals.length, fields: fields.length, methods: methods.length }, outside: !local,
          tooltip: `${entity.kind}: ${entity.qualified_name}. ${entity.presence}. ${entity.responsibilities.join(" ")}` };
      });
      const edges = [...groups.values()].map((edge) => {
        const assessments = [...new Map([...edge.assessments, ...(comparison?.assessments.filter((item) =>
          edge.sites.some((site) => edge.sourceGraph.origin === G.OriginKind.OBSERVED
            ? item.observed_ids.includes(site.id) : site.id === item.subject_id)) || [])]
          .map((item) => [item.id, item])).values()];
        const observedSites = [...new Set((comparison?.assessments || [])
          .filter((match) => edge.sites.some((site) => site.id === match.subject_id))
          .flatMap((match) => match.observed_ids))].map((id) => DATA.observed?.relationships.find((site) => site.id === id)).filter((site) => site !== undefined);
        const findings = (viewMode === P.ViewMode.TARGET ? [] : DATA.findings || []).filter((item) => [...edge.sites, ...observedSites]
          .some((site) => item.graph_subject_ids.includes(site.id)));
        const statuses = [...new Set([...assessments, ...findings].map((item) => item.status))];
        const decisionGaps = (DATA.decision_gaps || []).filter((gap) => edge.sourceGraph.origin === G.OriginKind.OBSERVED
          && edge.sites.some((site) => gap.relationship_ids.includes(site.id)));
        return { ...edge, observedSites, assessments, findings, decisionGaps,
          state: statuses.includes(G.AssessmentStatus.FAIL) ? P.EdgeState.VIOLATION : statuses.includes(G.AssessmentStatus.UNKNOWN) || decisionGaps.length ? P.EdgeState.UNDECIDED : edge.state,
          tooltip: `${edge.relationshipKind === G.RelationshipKind.REQUIRES ? "Allowed component import" : edge.relationshipKind}${edge.resolution === G.ResolutionKind.PARTIAL ? " candidate; not confirmed" : ""}: ${
            endpointName(edge.sourceGraph, edge.sites[0].source_id)} → ${
            endpointName(edge.sourceGraph, edge.sites[0].target_id || edge.sites[0].candidate_ids[0])}; ${
            edge.sites.length + observedSites.length} source or declaration site${edge.sites.length + observedSites.length === 1 ? "" : "s"}.${statuses.length ? ` Core ${statuses.join("/")}${assessments.some((item) => item.change === G.AssessmentChange.UNEXPECTED) ? " · unlisted observed relationship" : ""}.` : ""}`,
        };
      });
      return { nodes, frames: [], edges, owner: scope, componentOverview };
    }

    /** @returns {Entity[]} */
    function unassignedArchitectureModules() {
      const components = new Set(componentIntents(DATA.target).map((item) => item.component_id));
      const observed = DATA.observed;
      if (!observed) return [];
      return observed.entities.filter((item) => {
        const parent = architectureParent(item, observed);
        return item.kind === G.EntityKind.MODULE && item.presence === G.PresenceKind.DEFINED
          && (parent === null || !components.has(parent));
      })
        .sort((left, right) => (left.file_path || left.qualified_name).localeCompare(right.file_path || right.qualified_name));
    }

    return {
      entities: architectureEntities, entity: architectureEntity, parent: architectureParent,
      label: architectureLabel, member: umlMember, hasInterior: architectureHasInterior,
      assessments: architectureAssessments, projectArchitectureScene,
      unassignedModules: unassignedArchitectureModules,
    };
  }
  return { create };
})();
