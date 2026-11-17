"use strict";
(function (global) {
  // The routes of UML relationships between placed boxes live in report-routes.js.
  const { orthogonalPath, routeUmlRelationships } = global.ArchkeelReportRoutes;
  let engine = null;
  // The layout blocks the page; one painted frame first lets the canvas show that it is arranging.
  const painted = () => new Promise((done) => {
    if (typeof requestAnimationFrame !== "function" || document.hidden) done();
    else requestAnimationFrame(() => setTimeout(done, 0));
  });
  async function layout(graph) {
    if (!engine) {
      if (typeof ELK !== "function") throw new Error("The pinned ELK layout engine is unavailable.");
      engine = new ELK();
    }
    await painted();
    return engine.layout(graph);
  }
  function absolutePosition(graph, offsetX, offsetY, rootId) {
    const x = graph.id === rootId && graph.x === undefined ? 0 : graph.x;
    const y = graph.id === rootId && graph.y === undefined ? 0 : graph.y;
    if (!Number.isFinite(x) || !Number.isFinite(y)) throw new Error(`ELK returned invalid coordinates for ${graph.id}.`);
    return [offsetX + x, offsetY + y];
  }
  function routeSections(sections, offsetX, offsetY, id) {
    if (!sections.length) throw new Error(`ELK did not route active relationship ${id}.`);
    const paths = sections.map((section) => [section.startPoint,
      ...(section.bendPoints || []), section.endPoint].map((point) => [point.x + offsetX, point.y + offsetY]));
    const points = paths.flat();
    if (points.length < 2 || points.some(([x, y]) => !Number.isFinite(x) || !Number.isFinite(y))) {
      throw new Error(`ELK returned an invalid route for relationship ${id}.`);
    }
    const mid = points[Math.floor(points.length / 2)];
    return { points, mid, d: paths.map(orthogonalPath).join(" "), lx: mid[0], ly: mid[1] - 8 };
  }
  function hasCompleteManualPositions(nodeIds, positions) {
    return nodeIds.length > 0 && nodeIds.every((id) => Object.hasOwn(positions, id)
      && Number.isFinite(positions[id]?.x) && Number.isFinite(positions[id]?.y));
  }
  function decodeLayout(result, { nodeIds, frameIds, edgeIds, labelIds = [] }) {
    const expectedNodes = new Set(nodeIds), expectedFrames = new Set(frameIds);
    const expectedEdges = new Set(edgeIds), expectedLabels = new Set(labelIds);
    const positions = Object.create(null), frames = Object.create(null);
    const routes = new Map(), labels = Object.create(null);
    const pendingEdges = new Map(), origins = new Map();
    function readLabels(items, x, y) {
      for (const label of items) {
        if (!expectedLabels.has(label.id)) throw new Error(`ELK returned an unexpected layout label ${label.id}.`);
        if (Object.hasOwn(labels, label.id)) throw new Error(`ELK duplicated active layout label ${label.id}.`);
        if (![label.x, label.y, label.width, label.height].every(Number.isFinite)
            || label.width <= 0 || label.height <= 0) {
          throw new Error(`ELK returned invalid geometry for label ${label.id}.`);
        }
        labels[label.id] = { x: x + label.x, y: y + label.y,
          width: label.width, height: label.height };
      }
    }
    const walk = (graph, offsetX = 0, offsetY = 0, isRoot = false, parentId = null) => {
      const [x, y] = absolutePosition(graph, offsetX, offsetY, isRoot ? result.id : "");
      origins.set(graph.id, [x, y]);
      if (!isRoot) {
        if (expectedNodes.has(graph.id)) {
          if (Object.hasOwn(positions, graph.id)) throw new Error(`ELK duplicated active layout node ${graph.id}.`);
          positions[graph.id] = { x, y };
        } else if (expectedFrames.has(graph.id)) {
          if (Object.hasOwn(frames, graph.id)) throw new Error(`ELK duplicated active layout frame ${graph.id}.`);
          if (!Number.isFinite(graph.width) || !Number.isFinite(graph.height) || graph.width <= 0 || graph.height <= 0) {
            throw new Error(`ELK returned invalid bounds for frame ${graph.id}.`);
          }
          frames[graph.id] = {
            parentId, left: x, right: x + graph.width, top: y, bottom: y + graph.height,
          };
        } else throw new Error(`ELK returned an unexpected layout node ${graph.id}.`);
      }
      readLabels(graph.labels || [], x, y);
      for (const edge of graph.edges || []) {
        if (!expectedEdges.has(edge.id)) throw new Error(`ELK returned an unexpected layout relationship ${edge.id}.`);
        if (pendingEdges.has(edge.id)) throw new Error(`ELK duplicated layout relationship ${edge.id}.`);
        pendingEdges.set(edge.id, { edge, container: edge.container ?? graph.id });
      }
      for (const child of graph.children || []) walk(child, x, y, false, graph.id);
    };
    walk(result, 0, 0, true);
    // ELK can store an edge at the root while its coordinates belong to a nested container.
    for (const { edge, container } of pendingEdges.values()) {
      if (container !== result.id && !Object.hasOwn(frames, container)) {
        throw new Error(`ELK returned an unknown edge container ${container}.`);
      }
      const [x, y] = origins.get(container);
      routes.set(edge.id, routeSections(edge.sections || [], x, y, edge.id));
      readLabels(edge.labels || [], x, y);
    }
    if ([...expectedNodes].some((id) => !Object.hasOwn(positions, id)) || Object.keys(positions).length !== expectedNodes.size) {
      throw new Error("ELK did not place every active layout node.");
    }
    if ([...expectedFrames].some((id) => !Object.hasOwn(frames, id)) || Object.keys(frames).length !== expectedFrames.size) {
      throw new Error("ELK did not place every active layout frame.");
    }
    if ([...expectedEdges].some((id) => !routes.has(id)) || routes.size !== expectedEdges.size) {
      throw new Error("ELK did not route every active layout relationship.");
    }
    if ([...expectedLabels].some((id) => !Object.hasOwn(labels, id)) || Object.keys(labels).length !== expectedLabels.size) {
      throw new Error("ELK did not place every active layout label.");
    }
    return { positions, frames, routes, labels };
  }
  // The shape of the view that the rows fill: the width over the height of the canvas, times 1.45
  // (the cards are taller than wide, and the edges need room between the layers), within 1.2 and 3.
  function viewAspect() {
    const canvas = typeof document === "undefined" ? null : document.querySelector("#flow .flow-canvas");
    if (!canvas || !canvas.clientWidth || !canvas.clientHeight) return 2.4;
    return Math.round(Math.min(3, Math.max(1.2, (canvas.clientWidth / canvas.clientHeight) * 1.45)) * 10) / 10;
  }
  // The width of an edge label in its font (`.atlas-edge-label`: 11px of the sans font).
  let labelContext = null;
  function labelWidth(text) {
    if (typeof document === "undefined") return text.length * 6.2;
    if (!labelContext) {
      labelContext = document.createElement("canvas").getContext("2d");
      const sans = getComputedStyle(document.documentElement).getPropertyValue("--font-sans").trim();
      labelContext.font = `11px ${sans || "sans-serif"}`;
    }
    return Math.ceil(labelContext.measureText(text).width);
  }
  function buildAtlasGraph({ componentOverview, parentId, nodes, edges, components, cardWidth, cardHeights }) {
    const rootId = "__archkeel_atlas_layout_root__";
    const componentsById = new Map(components.map((component) => [component.id, component]));
    const nodeLayoutId = (id) => `${componentOverview ? "component" : "module"}:${id}`;
    const componentLayoutId = (id) => `component:${id}`;
    const layoutOptions = {
      "elk.algorithm": "layered", "elk.direction": "RIGHT",
      "elk.hierarchyHandling": "INCLUDE_CHILDREN", "elk.edgeRouting": "ORTHOGONAL",
      "elk.layered.cycleBreaking.strategy": "GREEDY",
      "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
      "elk.separateConnectedComponents": "true", "elk.spacing.nodeNode": "24",
      "elk.layered.spacing.nodeNodeBetweenLayers": "68",
      "elk.padding": "[top=28,left=28,bottom=28,right=28]",
    };
    // A chain of boxes, or boxes with no edge, would stand in one row at a small zoom. Without a
    // layer order, the layered layout wraps them into rows that fill the view (wide as the
    // window: 2.4), and a chain snakes from row to row with its edges following. Module boxes with
    // no component frame between them and the level wrap the same way.
    const wraps = componentOverview ? !nodes.some((node) => node.id.startsWith("LAYER:"))
      : nodes.every((node) => !node.ownerId || node.ownerId === parentId || !componentsById.has(node.ownerId));
    if (wraps) {
      Object.assign(layoutOptions, {
        "elk.layered.wrapping.strategy": "MULTI_EDGE", "elk.aspectRatio": String(viewAspect()),
        "elk.layered.spacing.nodeNodeBetweenLayers": "50",
      });
    }
    // Boxes with no edge between them: the layered layout puts each in its own component and
    // stacks them in one column; packing fills rows in the shape of the view (issue 1618).
    if (wraps && !edges.length) {
      for (const key of Object.keys(layoutOptions)) if (key.startsWith("elk.layered.")) delete layoutOptions[key];
      layoutOptions["elk.algorithm"] = "rectpacking";
    }
    const labels = [];
    const graphEdges = edges.map((edge) => {
      const id = componentOverview ? `edge:${edge.layoutId}` : `edge:${edge.id}`;
      const graphEdge = { id,
        sources: [nodeLayoutId(edge.source)], targets: [nodeLayoutId(edge.target)] };
      if (componentOverview) {
        // The label gets the width of its text, so the layout keeps room for all of it between
        // the boxes and draws it on the middle of the edge (issue 1659).
        const label = { id: `label:${edge.layoutId}`, text: edge.label,
          width: Math.max(24, labelWidth(edge.label) + 8), height: 16 };
        graphEdge.labels = [label];
        labels.push(label.id);
      }
      return graphEdge;
    });
    if (componentOverview) {
      const graph = {
        id: rootId,
        children: nodes.map((node) => ({ id: nodeLayoutId(node.id),
          width: cardWidth, height: cardHeights[node.id] })),
        edges: graphEdges,
        layoutOptions,
      };
      return { graph, expected: {
        nodeIds: nodes.map((node) => nodeLayoutId(node.id)), frameIds: [],
        edgeIds: graphEdges.map((edge) => edge.id), labelIds: labels,
      } };
    }

    const included = new Set();
    for (const node of nodes) {
      for (let id = node.ownerId; id && id !== parentId;) {
        const component = componentsById.get(id);
        if (!component) break;
        included.add(id);
        id = component.parentId;
      }
    }
    const childrenByOwner = new Map();
    const append = (owner, child) => {
      if (!childrenByOwner.has(owner)) childrenByOwner.set(owner, []);
      childrenByOwner.get(owner).push(child);
    };
    for (const node of nodes) {
      const owner = included.has(node.ownerId) ? componentLayoutId(node.ownerId) : rootId;
      const id = nodeLayoutId(node.id);
      const label = { id: `label:${id}`, text: node.label,
        width: cardWidth - 16, height: 34 };
      labels.push(label.id);
      append(owner, { id, width: cardWidth, height: cardHeights[node.id], labels: [label] });
    }
    for (const id of included) {
      const component = componentsById.get(id);
      const parent = included.has(component.parentId) ? componentLayoutId(component.parentId) : rootId;
      const layoutId = componentLayoutId(id);
      const label = { id: `label:${layoutId}`, text: component.label,
        width: Math.min(250, Math.max(100, component.label.length * 7)), height: 20 };
      labels.push(label.id);
      append(parent, { id: layoutId, labels: [label], children: childrenByOwner.get(layoutId) || [],
        layoutOptions: { "elk.padding": "[top=52,left=20,bottom=20,right=20]" } });
    }
    return { graph: {
      id: rootId, children: childrenByOwner.get(rootId) || [], edges: graphEdges, layoutOptions,
    }, expected: {
      nodeIds: nodes.map((node) => nodeLayoutId(node.id)),
      frameIds: [...included].map(componentLayoutId),
      edgeIds: graphEdges.map((edge) => edge.id), labelIds: labels,
    } };
  }
  function buildUmlGraph({ nodes, edges, cardWidth, cardHeights, edgeSpacing = 10 }) {
    const nodeIds = nodes.map((node) => `node:${node.id}`);
    const edgeIds = edges.map((edge) => `edge:${edge.id}`);
    const knownNodes = new Set(nodes.map((node) => node.id));
    const graphEdges = edges.map((edge) => {
      if (!knownNodes.has(edge.source) || !knownNodes.has(edge.target)) {
        throw new Error(`UML relationship ${edge.id} has a missing layout endpoint.`);
      }
      return { id: `edge:${edge.id}`, sources: [`node:${edge.source}`], targets: [`node:${edge.target}`] };
    });
    return {
      graph: {
        id: "__archkeel_uml_layout_root__",
        children: nodes.map((node) => ({ id: `node:${node.id}`, width: cardWidth,
          height: cardHeights[node.id] })),
        edges: graphEdges,
        layoutOptions: {
          "elk.algorithm": "layered", "elk.direction": "RIGHT",
          "elk.hierarchyHandling": "INCLUDE_CHILDREN", "elk.edgeRouting": "ORTHOGONAL",
          "elk.layered.cycleBreaking.strategy": "GREEDY",
          "elk.layered.crossingMinimization.strategy": "LAYER_SWEEP",
          "elk.separateConnectedComponents": "true", "elk.spacing.nodeNode": "24",
          "elk.layered.spacing.nodeNodeBetweenLayers": "68",
          "elk.layered.spacing.edgeNodeBetweenLayers": "16",
          "elk.spacing.edgeEdge": String(edgeSpacing),
          "elk.layered.spacing.edgeEdgeBetweenLayers": String(edgeSpacing),
          "elk.padding": "[top=28,left=28,bottom=28,right=28]",
        },
      },
      expected: { nodeIds, frameIds: [], edgeIds, labelIds: [] },
    };
  }
  async function layoutUml(input) {
    const { graph, expected } = buildUmlGraph(input);
    return decodeLayout(await layout(graph), expected);
  }
  async function layoutAtlas(input) {
    // The label widths are measured in the font of the page, so the font must be loaded first.
    if (typeof document !== "undefined" && document.fonts) await document.fonts.ready;
    const { graph, expected } = buildAtlasGraph(input);
    const result = await layout(graph);
    const decoded = decodeLayout(result, expected);
    if (input.componentOverview) straightenStackedEdges(decoded, input);
    return { ...decoded, bounds: { width: result.width, height: result.height } };
  }
  // A wrapped row puts boxes above each other, and ELK routes the edge between them around the
  // row: right, down, back left and in from the side. Two boxes that stand above each other with
  // no box between them get a straight vertical edge, and the label moves next to it.
  function straightenStackedEdges({ positions, routes, labels }, { edges, cardWidth, cardHeights }) {
    const box = (id) => {
      const point = positions[`component:${id}`];
      return { left: point.x, right: point.x + cardWidth, top: point.y, bottom: point.y + cardHeights[id] };
    };
    const boxes = Object.keys(cardHeights).map((id) => ({ id, ...box(id) }));
    const pairs = new Map();
    for (const edge of edges) {
      if (edge.source === edge.target) continue;
      const key = [edge.source, edge.target].sort().join("\0");
      if (!pairs.has(key)) pairs.set(key, []);
      pairs.get(key).push(edge);
    }
    for (const group of pairs.values()) {
      const [a, b] = [box(group[0].source), box(group[0].target)];
      const [upper, lower] = a.top <= b.top ? [a, b] : [b, a];
      const left = Math.max(a.left, b.left) + 16, right = Math.min(a.right, b.right) - 16;
      if (right <= left || upper.bottom >= lower.top) continue;
      const between = boxes.some((other) => other.left < right && other.right > left
        && other.top < lower.top && other.bottom > upper.bottom);
      if (between) continue;
      group.forEach((edge, index) => {
        const x = left + ((right - left) * (index + 1)) / (group.length + 1);
        const down = box(edge.source).top <= box(edge.target).top;
        const points = down ? [[x, upper.bottom], [x, lower.top]] : [[x, lower.top], [x, upper.bottom]];
        const mid = [x, (upper.bottom + lower.top) / 2];
        routes.set(`edge:${edge.layoutId}`, { points, mid, d: orthogonalPath(points), lx: mid[0], ly: mid[1] - 8 });
        const label = labels[`label:${edge.layoutId}`];
        if (label) Object.assign(label, { x: x + 6, y: mid[1] - label.height / 2 });
      });
    }
  }
  global.ArchkeelReportLayout = {
    layout, decodeLayout, buildAtlasGraph,
    layoutUml, layoutAtlas, routeUmlRelationships, hasCompleteManualPositions,
  };
})(window);
