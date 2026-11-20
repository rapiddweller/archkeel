import { canvas, cards, details, get, showError, viewport } from "./studio-dom.js";
import { state } from "./studio-state.js";
import { api } from "./studio-api.js";
import { focusMap, mapCardWidth, mapEdgeName, mapView, paintMapScene } from "./explorer-map.js";
import { treeMapAnchor } from "./explorer-tree.js";
let mapLayout = "groups";
let layoutSwitch = 0;
function mapGraph(parent, response, mode) {
    const { items, groups = [], edges } = response;
    const included = new Set([...items, ...groups].map((node) => node.id));
    const graphEdges = edges.filter((edge) => !!edge.target && included.has(edge.source) && included.has(edge.target)
        && edge.source !== edge.target);
    const compact = !graphEdges.length || mode === "groups" && (groups.length > 0 || items.length > 2);
    const graphRoot = "map-root";
    const children = new Map();
    const width = Math.max(400, (viewport.clientWidth || 1200) - details.clientWidth - 80);
    const height = viewport.clientHeight || 700;
    const aspect = String(Math.max(1.2, Math.min(3, width / height * 1.45)));
    const options = {
        "elk.algorithm": !compact && graphEdges.length ? "layered" : "rectpacking",
        "elk.direction": mode === "down" ? "DOWN" : "RIGHT", "elk.hierarchyHandling": "INCLUDE_CHILDREN",
        "elk.edgeRouting": "ORTHOGONAL", "elk.padding": "[top=38,left=38,bottom=36,right=38]",
        "elk.separateConnectedComponents": "true", "elk.spacing.nodeNode": "40",
        "elk.layered.spacing.nodeNodeBetweenLayers": "94",
        "elk.rectpacking.widthApproximation.targetWidth": String(Math.max(400, Math.floor(width * .88))),
        "elk.aspectRatio": aspect,
    };
    const nodeId = (id) => "node:" + id;
    const groupChildren = (id) => {
        const existing = children.get(id);
        if (existing)
            return existing;
        const nodes = [];
        children.set(id, nodes);
        return nodes;
    };
    const append = (owner, node) => {
        const id = owner && owner !== parent && included.has(owner) ? nodeId(owner) : graphRoot;
        groupChildren(id).push(node);
    };
    for (const group of groups) {
        const id = nodeId(group.id);
        append(group.parent, {
            id, children: groupChildren(id), width: mapCardWidth, height: 64,
            layoutOptions: {
                "elk.algorithm": "rectpacking",
                "elk.padding": "[top=52,left=22,bottom=22,right=22]", "elk.aspectRatio": "0.8",
                "elk.rectpacking.widthApproximation.targetWidth": "400",
            },
        });
    }
    for (const item of items) {
        append(item.parent, {
            id: nodeId(item.id), width: mapCardWidth,
            height: (item.kind === "component" && item.responsibilities?.length ? 120 : 87)
                + (Number.isInteger(item.module_count) ? 25 : 0)
                + (item.kind === "component" && item.public?.length ? 36 : 0)
                + ((item.unresolved_calls ?? 0) > 0 ? 23 : 0),
        });
    }
    // A stable subset guides dense placement. Every measured edge remains available for focus.
    const represented = (compact ? [] : placementEdges(graphEdges)).map((edge) => {
        const text = mapEdgeName(edge);
        return { id: edge.id, sources: [nodeId(edge.source)], targets: [nodeId(edge.target)],
            labels: [{ id: "label:" + edge.id, text, width: Math.min(225, text.length * 7 + 16), height: 26 }] };
    });
    return {
        graph: { id: graphRoot, children: children.get(graphRoot) ?? [], edges: represented, layoutOptions: options },
        expected: {
            nodeIds: items.map((item) => nodeId(item.id)), frameIds: groups.map((group) => nodeId(group.id)),
            edgeIds: represented.map(({ id }) => id), labelIds: represented.flatMap((edge) => edge.labels?.map(({ id }) => id) ?? []),
        },
        edges: graphEdges,
    };
}
function placementEdges(edges) {
    if (edges.length <= 28)
        return edges;
    const degree = new Map();
    return [...edges].sort((a, b) => (b.count ?? 1) - (a.count ?? 1) || a.id.localeCompare(b.id))
        .filter((edge) => {
        const count = degree.get(edge.source) ?? 0;
        if (count === 2)
            return false;
        degree.set(edge.source, count + 1);
        return true;
    }).slice(0, 28);
}
export async function layoutMap(response, mode = mapLayout) {
    const { graph, expected, edges } = mapGraph(response.parent, response, mode);
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
export function mapRoutes(layout, edges) {
    if (edges.every((edge) => layout.routes.has(edge.id)))
        return layout.routes;
    const withoutPrefix = (id) => id.slice(5);
    const positions = Object.fromEntries(Object.entries(layout.positions).map(([id, at]) => [withoutPrefix(id), at]));
    const frames = Object.fromEntries(Object.entries(layout.frames).map(([id, bounds]) => [withoutPrefix(id), { ...bounds, header: 36 }]));
    for (const [id, frame] of Object.entries(frames))
        positions[id] = { x: frame.left, y: frame.top };
    const nodeSizes = Object.fromEntries(layout.graphNodes.filter((node) => !node.children).map(({ id, width, height }) => [withoutPrefix(id), { width, height }]));
    const result = globalThis.ArchkeelReportLayout.routeUmlRelationships({
        positions, nodeSizes, edges: edges.map((edge) => ({ ...edge, relationshipKind: edge.kind === "call" ? "calls" : edge.kind })),
        frames, cardWidth: mapCardWidth, gap: 24, laneGap: 18, rowGap: 34,
    });
    return new Map(result.map((route) => [route.edgeId, route]));
}
export function showMapLayoutControls(show) {
    const controls = get("map-layouts");
    controls.hidden = !show;
    for (const button of controls.querySelectorAll("button")) {
        button.setAttribute("aria-pressed", String(button.dataset.mapLayout === mapLayout));
    }
}
export function bindMapLayouts() {
    get("map-layouts").addEventListener("click", (event) => {
        if (!(event.target instanceof Element))
            return;
        const mode = event.target.closest("button")?.dataset.mapLayout;
        if (mode === "groups" || mode === "right" || mode === "down")
            switchMapLayout(mode).catch(showError);
    });
}
async function switchMapLayout(mode) {
    const previous = mapView.scene;
    if (!previous?.plane.isConnected)
        return;
    const ticket = ++layoutSwitch;
    if (mode === mapLayout)
        return;
    const request = state.request;
    const response = mapView.response;
    if (!response)
        return;
    const result = await layoutMap(response, mode);
    if (ticket !== layoutSwitch || previous !== mapView.scene || request !== state.request)
        return;
    const active = [...previous.plane.querySelectorAll(".map-active-edge")].map((edge) => edge.getAttribute("data-map-edge"));
    const scene = paintMapScene(result, response);
    mapView.scene = scene;
    mapLayout = mode;
    showMapLayoutControls(true);
    focusMap(state.selected);
    for (const link of scene.plane.querySelectorAll(".map-edges [data-map-edge]")) {
        if (active.includes(link.getAttribute("data-map-edge")))
            link.classList.add("map-active-edge");
    }
    zoomMap(0);
    panMapTo(treeMapAnchor(state.selected));
}
export function panMapTo(card) {
    if (!card)
        return;
    const box = card.getBoundingClientRect();
    const stage = viewport.getBoundingClientRect();
    const freeWidth = Math.max(200, stage.width - details.clientWidth);
    viewport.scrollBy(box.x - stage.x - (freeWidth - box.width) / 2, box.y - stage.y - (stage.height - box.height) / 2);
}
export function placeMapLabel(path, label, obstacles) {
    const halfWidth = label.offsetWidth / 2;
    const halfHeight = label.offsetHeight / 2;
    const length = path.getTotalLength();
    const candidates = [0.5, 0.4, 0.6, 0.3, 0.7, 0.2, 0.8].map((fraction) => {
        const { x, y } = path.getPointAtLength(length * fraction);
        const box = { left: x - halfWidth, top: y - halfHeight,
            right: x + halfWidth, bottom: y + halfHeight };
        const overlaps = obstacles.filter((other) => box.left < other.right &&
            box.right > other.left && box.top < other.bottom && box.bottom > other.top).length;
        return { x, y, box, overlaps };
    });
    const at = candidates.reduce((best, next) => next.overlaps < best.overlaps ? next : best);
    if (at.overlaps) {
        label.remove();
        return;
    }
    obstacles.push(at.box);
    mapPosition(label, at.x, at.y);
}
export function mapPosition(node, x, y, width, height) {
    node.style.left = x + "px";
    node.style.top = y + "px";
    if (width)
        node.style.width = width + "px";
    if (height)
        node.style.height = height + "px";
}
export function zoomMap(delta, whole = false) {
    const plane = cards.querySelector(".map-plane");
    if (!plane)
        return false;
    const inset = parseFloat(getComputedStyle(canvas).paddingInlineEnd);
    const canvasFit = (viewport.clientWidth - inset - 26) / plane.offsetWidth;
    const scale = delta
        ? Math.max(.12, Math.min(2.4, (parseFloat(plane.style.zoom) || 1) * (delta > 0 ? 1.2 : 1 / 1.2)))
        : Math.max(whole ? .12 : .78, Math.min(1.24, canvasFit, (viewport.clientHeight - 102) / plane.offsetHeight));
    plane.style.zoom = String(scale);
    get("zoom-level").textContent = Math.round(scale * 100) + "%";
    get("zoom-in").disabled = scale >= 2.4;
    get("zoom-out").disabled = scale <= .12;
    if (!delta)
        viewport.scrollTo(0, 0);
    return true;
}
export function mapPage(current, cursor, focus) {
    const view = current.id === "system" ? "components" : "hierarchy";
    return api("map", { parent: current.id, view, cursor, focus, limit: 36 });
}
export function inspector(open) {
    details.hidden = !open;
    get("inspector-toggle").setAttribute("aria-pressed", String(open));
}
