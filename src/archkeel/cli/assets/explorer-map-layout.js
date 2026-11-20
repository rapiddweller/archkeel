"use strict";

function mapGraph(parent, response) {
  const { items, groups = [], edges } = response;
  const included = new Set([...items, ...groups].map((node) => node.id));
  const graphEdges = edges.filter((edge) => included.has(edge.source) && included.has(edge.target)
    && edge.source !== edge.target);
  const compact = graphEdges.length > 16;
  const graphRoot = "map-root";
  const children = new Map();
  const width = viewport.clientWidth || 1200;
  const height = viewport.clientHeight || 700;
  const aspect = String(Math.max(1.2, Math.min(3, width / height * 1.45)));
  const options = {
    "elk.algorithm": !compact && graphEdges.length ? "layered" : "rectpacking",
    "elk.direction": "RIGHT", "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.edgeRouting": "ORTHOGONAL", "elk.padding": "[top=38,left=38,bottom=36,right=38]",
    "elk.separateConnectedComponents": "true", "elk.spacing.nodeNode": "40",
    "elk.layered.spacing.nodeNodeBetweenLayers": "94",
    "elk.aspectRatio": aspect,
  };
  const nodeId = (id) => "node:" + id;
  const append = (owner, node) => {
    const id = owner !== parent && included.has(owner) ? nodeId(owner) : graphRoot;
    if (!children.has(id)) children.set(id, []);
    children.get(id).push(node);
  };
  for (const group of groups) {
    const id = nodeId(group.id);
    if (!children.has(id)) children.set(id, []);
    append(group.parent, {
      id, children: children.get(id), width: mapCardWidth, height: 64,
      layoutOptions: { "elk.padding": "[top=52,left=22,bottom=22,right=22]", "elk.aspectRatio": "1.6" },
    });
  }
  for (const item of items) {
    append(item.parent, {
      id: nodeId(item.id), width: mapCardWidth,
      height: (item.kind === "component" && item.responsibilities?.length ? 120 : 87)
        + (Number.isInteger(item.module_count) ? 25 : 0)
        + (item.kind === "component" && item.public?.length ? 36 : 0)
        + (item.unresolved_calls > 0 ? 23 : 0),
    });
  }
  const represented = (compact ? [] : graphEdges).map((edge) => {
    const link = { id: edge.id, sources: [nodeId(edge.source)], targets: [nodeId(edge.target)] };
    const text = mapEdgeName(edge);
    link.labels = [{ id: "label:" + edge.id, text, width: Math.min(225, text.length * 7 + 16), height: 26 }];
    return link;
  });
  return {
    graph: { id: graphRoot, children: children.get(graphRoot) ?? [], edges: represented, layoutOptions: options },
    expected: {
      nodeIds: items.map((item) => nodeId(item.id)), frameIds: groups.map((group) => nodeId(group.id)),
      edgeIds: represented.map(({id}) => id), labelIds: represented.flatMap((edge) => edge.labels?.map(({id}) => id) ?? []),
    },
    edges: graphEdges,
  };
}

async function layoutMap(response) {
  const { graph, expected, edges } = mapGraph(response.parent, response);
  const placement = globalThis.ArchkeelReportPlacement;
  const model = await placement.layout(graph);
  const graphNodes = [];
  const walk = (item) => {
    graphNodes.push(item);
    item.children?.forEach(walk);
  };
  graph.children.forEach(walk);
  return { ...placement.decodeLayout(model, expected), width: model.width, height: model.height, graphNodes, edges };
}

function mapRoutes(layout, edges) {
  if (!edges.length || layout.routes.size) return layout.routes;
  const withoutPrefix = (id) => id.slice(5);
  const positions = Object.fromEntries(Object.entries(layout.positions).map(([id, at]) =>
    [withoutPrefix(id), at]));
  const frames = Object.fromEntries(Object.entries(layout.frames).map(([id, bounds]) =>
    [withoutPrefix(id), { ...bounds, header: 36 }]));
  for (const [id, frame] of Object.entries(frames)) positions[id] = { x: frame.left, y: frame.top };
  const nodeSizes = Object.fromEntries(layout.graphNodes.filter((node) => !node.children).map(({ id, width, height }) =>
    [withoutPrefix(id), { width, height }]));
  const result = globalThis.ArchkeelReportLayout.routeUmlRelationships({
    positions, nodeSizes, edges: edges.map((edge) => ({ ...edge, relationshipKind: edge.kind === "call" ? "calls" : edge.kind })),
    frames, cardWidth: mapCardWidth, gap: 24, laneGap: 18, rowGap: 34,
  });
  return new Map(result.map((route) => [route.edgeId, route]));
}
