import { button, canvas, cards, details, element, get, notice, showError, viewport } from "./studio-dom.js";
import { api } from "./studio-api.js";
import type { MapResponse, StudioEdge, StudioItem } from "./studio-model.js";
import { known, pageTrails, state, system } from "./studio-state.js";
import { label, open, relationLabel, select, showEvidence } from "./explorer.js";
import { showScope } from "./explorer-navigation.js";
import { bindMapLayouts, layoutMap, mapRoutes, placeMapLabel, showMapLayoutControls } from "./explorer-map-layout.js";
import type { MapLayout, MapScene } from "./explorer-map-layout.js";
import { storyChat } from "./explorer-story.js";
import { markTreeSelection, paintStructure, treeMapAnchor } from "./explorer-tree.js";
import { canOpenScope, paintCards, umlCard } from "./explorer-uml.js";

export const mapView: { mode: "components" | "modules"; response: MapResponse | null; scene: MapScene | null; treeOpen: boolean } = { mode: "components", response: null, scene: null, treeOpen: false };
export const mapCardWidth = 224;

export function derivedMapGroup(item: StudioItem | undefined) {
  return !!item && ["layer", "directory"].includes(item.kind);
}

export function mapScope(item: StudioItem, query: string | null) {
  return !query && (["system", "component"].includes(item.kind) || derivedMapGroup(item));
}

export function mapSearchArgs(parent: string, text: string) {
  return mapView.response?.scope_truncated && mapView.response.parent === parent
    ? { text, parent } : { text };
}

export function inspector(open: boolean) {
  details.hidden = !open;
  get("inspector-toggle").setAttribute("aria-pressed", String(open));
}

function structure(open: boolean) {
  get("structure-pane").hidden = !open;
  get("structure-toggle").setAttribute("aria-pressed", String(open));
}

export function setStoryLink(id: string | null) {
  const url = new URL(location.href);
  if (id) url.searchParams.set("story", id);
  else url.searchParams.delete("story");
  if (url.href !== location.href) history.replaceState(null, "", url);
}

export function setMapControls(active: boolean, overview = false) {
  get("structure-tree").replaceChildren();
  showMapLayoutControls(false);
  get("map-modes").hidden = !overview || derivedMapGroup(state.ancestors.at(-1));
  get("map-components").setAttribute("aria-pressed", String(mapView.mode === "components"));
  get("map-modules").setAttribute("aria-pressed", String(mapView.mode === "modules"));
  if (!active) {
    structure(false);
    inspector(true);
  } else structure(mapView.treeOpen);
}

export function setMapTree(current: StudioItem, response: { items: StudioItem[] }, query: string | null) {
  if (query) structure(false);
  get("structure-toggle").disabled = Boolean(query);
  paintStructure({ parent: current.id, items: query ? [] : response.items });
}

export function mapParents(item: StudioItem) {
  const current = state.ancestors.at(-1)?.id ?? system.id;
  const ancestors: StudioItem[] = [];
  let owner = known.get(item.parent ?? "");
  while (owner && owner.id !== current && !state.ancestors.includes(owner) && !ancestors.includes(owner)) {
    ancestors.unshift(owner);
    owner = known.get(owner.parent ?? "");
  }
  return [...state.ancestors, ...ancestors.filter(canOpenScope), item];
}

export function mapEdgeName(edge: StudioEdge) {
  const name = edge.title ?? relationLabel(edge);
  return edge.count && edge.count > 1 ? name + " × " + edge.count.toLocaleString() : name;
}

export function relationDirection(edge: StudioEdge, current?: string | null) {
  const directions: Record<string, [string, string]> = {
    call: ["calls", "called by"],
    import: ["imports", "imported by"],
    import_site: ["imports", "imported by"],
    requires: ["requires", "required by"],
    interface: ["declares an interface to", "declared interface from"],
  };
  const [outbound, inbound] = directions[edge.kind] ?? ["→", "←"];
  const from = label(edge.source);
  const to = edge.target ? label(edge.target) : "UNKNOWN target";
  if (current === edge.target) return inbound + " " + from;
  if (current === edge.source) return outbound + " " + to;
  return from + " " + outbound + " " + to;
}

export function unknownCalls(item: StudioItem, compact = false) {
  const total = item.recorded_calls;
  if (!total || !item.unresolved_calls) return null;
  const missing = item.unresolved_calls.toLocaleString();
  const badge = element("span", "", "map-call-count");
  badge.append(element("span", missing, "unknown"), " / " + total.toLocaleString() +
    (compact ? " unresolved" : " calls unresolved"));
  badge.title = (total - item.unresolved_calls).toLocaleString() + " calls have a resolved target. " +
    missing + " calls have no verified target symbol. This includes built-ins and library calls when the scanner cannot link them to a symbol. Counts include child scopes.";
  return badge;
}

function componentPublic(item: StudioItem) {
  const section = document.createDocumentFragment();
  if (item.kind === "component" && item.public?.length) {
    section.append(element("h3", "Declared public surface"));
    for (const name of item.public) section.append(element("p", name, "meta"));
  }
  return section;
}

export function appendSelectionNotes(item: StudioItem) {
  for (const responsibility of item.responsibilities ?? []) details.append(element("p", responsibility));
  details.append(componentPublic(item), mapConnections(item.id));
  if (!derivedMapGroup(item)) details.append(storyChat(null, item.id), element("h3", "Connections"));
}

export function mapSvg<K extends keyof SVGElementTagNameMap>(name: K, attributes: Record<string, string | number>, parent: Element) {
  const item = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, String(value));
  parent.append(item);
  return item;
}

export function mapPosition(node: HTMLElement, x: number, y: number, width?: number, height?: number) {
  node.style.left = x + "px";
  node.style.top = y + "px";
  if (width) node.style.width = width + "px";
  if (height) node.style.height = height + "px";
}

function mapCard(item: StudioItem) {
  const card = umlCard(item);
  if (item.collapsed) card.classList.add("map-collapsed");
  const head = card.querySelector(".uml-head");
  if (!head) throw new Error("The map card has no heading.");
  if (item.kind === "module" && item.path) {
    const name = head.querySelector(".uml-name");
    if (name) name.textContent = item.path.split("/").at(-1) ?? item.name;
    head.append(element("span", item.path, "map-card-path"));
  }
  if (item.module_count !== undefined && Number.isInteger(item.module_count)) {
    const mark = element("span", item.module_count.toLocaleString() + (item.module_count === 1 ? " module" : " modules"),
      "map-component-meta");
    head.append(mark);
  }
  if (item.kind === "component" && item.public?.length) {
    const entry = element("span", "Public · " + item.public[0], "map-public-entry");
    entry.title = item.public[0];
    head.append(entry);
  }
  const unresolved = unknownCalls(item);
  if (unresolved) head.append(unresolved);
  return card;
}

export function paintMapScene(layout: MapLayout, response: MapResponse): MapScene {
  const plane = element("section", "", "map-plane");
  plane.setAttribute("aria-label", "Architecture graph");
  mapPosition(plane, 0, 0, layout.width, layout.height);
  const svg = mapSvg("svg", { class: "map-edges", width: layout.width, height: layout.height, "aria-hidden": "true" }, plane);
  const marker = mapSvg("marker", {
    id: "map-arrow", viewBox: "0 0 13 11", refX: "13", refY: "5.5", markerWidth: "13",
    markerHeight: "11", markerUnits: "userSpaceOnUse", orient: "auto",
  }, mapSvg("defs", {}, svg));
  mapSvg("path", { d: "M0 0 L13 5.5 L0 11 Z" }, marker);
  const containers = new Map<string, HTMLElement>();
  const ensureContainer = (id: string): HTMLElement => {
    const existing = containers.get(id);
    if (existing) return existing;
    const group = known.get(id);
    if (!group) throw new Error("The map group is missing: " + id);
    const frame = layout.frames["node:" + id];
    const owner = layout.frames["node:" + group.parent];
    const parent = owner && group.parent ? ensureContainer(group.parent) : plane;
    const section = element("section", "", "map-group " + group.kind);
    section.setAttribute("aria-label", group.name);
    section.dataset.group = id;
    const title = button("", () => select(group));
    title.className = "map-group-title";
    title.title = group.name;
    title.dataset.element = id;
    title.setAttribute("aria-pressed", String(id === state.selected));
    title.addEventListener("dblclick", () => open(group).catch(showError));
    title.append(element("small", group.kind), element("strong", group.name));
    const unresolved = unknownCalls(group, true);
    if (unresolved) title.append(unresolved);
    section.append(title);
    mapPosition(section, frame.left - (owner?.left ?? 0), frame.top - (owner?.top ?? 0),
      frame.right - frame.left, frame.bottom - frame.top);
    parent.append(section);
    containers.set(id, section);
    return section;
  };
  for (const group of response.groups ?? []) ensureContainer(group.id);
  const sizes = new Map(layout.graphNodes.map((node) => [node.id, node]));
  for (const item of response.items) {
    const at = layout.positions["node:" + item.id];
    const parent = layout.frames["node:" + item.parent];
    const card = mapCard(item);
    const size = sizes.get("node:" + item.id);
    if (!size) throw new Error("The map item has no size: " + item.id);
    mapPosition(card, at.x - (parent?.left ?? 0), at.y - (parent?.top ?? 0), size.width, size.height);
    (containers.get(item.parent ?? "") ?? plane).append(card);
  }
  cards.replaceChildren(plane);
  return { plane, svg, layout };
}

function openMapEvidence(edge: StudioEdge) {
  const plane = mapView.scene?.plane;
  for (const link of plane?.querySelectorAll(".map-edges [data-map-edge]") ?? []) {
    if (link.getAttribute("data-map-edge") === edge.id) link.classList.add("map-active-edge");
  }
  return showEvidence(edge);
}

function paintMapConnections(scene: MapScene, edges: MapLayout["edges"], animate = false) {
  const { plane, svg, layout } = scene;
  for (const edge of plane.querySelectorAll("[data-map-edge]")) edge.remove();
  const routes = mapRoutes(layout, edges);
  const obstacles = layout.graphNodes.filter((node) => !node.children).map(({ id, width, height }) => {
    const { x, y } = layout.positions[id];
    return { left: x, top: y, right: x + width, bottom: y + height };
  });
  for (const edge of edges) {
    const route = routes.get(edge.id);
    if (!route) throw new Error("The map edge has no route: " + edge.id);
    const group = mapSvg("g", { "data-map-edge": edge.id }, svg);
    const uncertain = edge.kind === "call" && edge.resolution !== "resolved";
    const style = uncertain ? "unknown" : edge.kind === "call" ? "map-proven" : edge.resolution;
    const path = mapSvg("path", { d: route.d, class: style, "marker-end": "url(#map-arrow)" }, group);
    if (!uncertain && edge.resolution === "resolved") {
      mapSvg("path", { d: route.d, class: "map-pulse", pathLength: "1" }, group);
      if (animate) group.classList.add("map-active-edge");
    }
    const label = button(mapEdgeName(edge), () => openMapEvidence(edge), "map-edge-label centered");
    if (uncertain) label.classList.add("map-unknown");
    label.title = relationDirection(edge) + " · " + relationLabel(edge);
    label.setAttribute("aria-label", mapEdgeName(edge) + " · " + label.title);
    label.dataset.mapEdge = edge.id;
    plane.append(label);
    placeMapLabel(path, label, obstacles);
  }
}
function mapContains(scope: string, endpoint: string | null) {
  const visited = new Set();
  for (let id: string | null | undefined = endpoint; id && !visited.has(id); id = known.get(id)?.parent) {
    if (scope === id) return true;
    visited.add(id);
  }
  return false;
}

function focusedMapEdges(id: string | null) {
  if (!id) return [];
  return (mapView.scene?.layout.edges ?? [])
    .filter((edge) => mapContains(id, edge.source) !== mapContains(id, edge.target))
    .sort((a, b) => (b.count ?? 1) - (a.count ?? 1));
}

function mapConnections(id: string) {
  const section = element("section", "");
  const edges = cards.querySelector<HTMLElement>(".map-plane") ? focusedMapEdges(id) : [];
  if (!edges.length) return section;
  section.append(element("h3", "On this map"));
  for (const edge of edges) {
    const outbound = mapContains(id, edge.source);
    const from = outbound ? edge.source : edge.target;
    section.append(button((outbound ? "→ " : "← ") + relationDirection(edge, from) + " · " + mapEdgeName(edge),
      () => openMapEvidence(edge), "detail-btn"));
  }
  return section;
}

export function focusMap(id: string | null) {
  markTreeSelection(id);
  const plane = cards.querySelector<HTMLElement>(".map-plane");
  if (!plane) return;
  const selection = id;
  id = treeMapAnchor(id)?.dataset.element ?? null;
  const response = mapView.response;
  const scene = mapView.scene;
  if (!scene || !response) return;
  const edges = scene.layout.edges;
  const neighbors = new Set(id ? [id] : []);
  const focused = focusedMapEdges(id);
  const scope = (key: string | null) => {
    for (let node = known.get(key ?? ""); node && !neighbors.has(node.id); node = known.get(node.parent ?? "")) {
      neighbors.add(node.id);
      if (node.id === response.parent) break;
    }
  };
  if (id) {
    neighbors.delete(id);
    scope(id);
    const below = new Set([id]);
    for (const node of [...(response.groups ?? []), ...response.items]) {
      for (let owner: StudioItem | undefined = node; owner && owner.id !== response.parent; owner = known.get(owner.parent ?? "")) {
        if (!below.has(owner.id)) continue;
        below.add(node.id);
        scope(node.id);
        break;
      }
    }
    for (const edge of focused) {
      scope(edge.source);
      scope(edge.target);
    }
  }
  for (const node of plane.querySelectorAll<HTMLElement>("[data-element], [data-group]")) {
    node.classList.toggle("map-dim", Boolean(id && !neighbors.has(node.dataset.element ?? node.dataset.group ?? "")));
    node.classList.toggle("map-context", id !== selection && node.dataset.element === id);
  }
  paintMapConnections(scene, edges.length <= 16 && !id ? edges : focused, Boolean(id));
}

export function zoomMap(delta: number, whole = false) {
  const plane = cards.querySelector<HTMLElement>(".map-plane");
  if (!plane) return false;
  const inset = parseFloat(getComputedStyle(canvas).paddingInlineEnd);
  const canvasFit = (viewport.clientWidth - inset - 26) / plane.offsetWidth;
  const scale = delta
    ? Math.max(.12, Math.min(2.4, (parseFloat(plane.style.zoom) || 1) * (delta > 0 ? 1.2 : 1 / 1.2)))
    : Math.max(whole ? .12 : .78, Math.min(1.24, canvasFit, (viewport.clientHeight - 102) / plane.offsetHeight));
  plane.style.zoom = String(scale);
  get("zoom-level").textContent = Math.round(scale * 100) + "%";
  get("zoom-in").disabled = scale >= 2.4;
  get("zoom-out").disabled = scale <= .12;
  if (!delta) viewport.scrollTo(0, 0);
  return true;
}

export function mapPage(current: StudioItem, cursor?: string | null) {
  const view = mapView.mode === "modules" || derivedMapGroup(current) ? "hierarchy" : "components";
  return api<MapResponse>("map", { parent: current.id, view, cursor, limit: 36 });
}

export async function showMapResponse(response: MapResponse, request: number, preparedLayout?: MapLayout) {
  mapView.response = response;
  for (const item of [...(response.groups ?? []), ...response.items]) known.set(item.id, item);
  if (!response.items.length) {
    paintStructure(response);
    return paintCards();
  }
  const layout = preparedLayout ?? await layoutMap(response);
  if (request !== state.request) return;
  mapView.scene = paintMapScene(layout, response);
  showMapLayoutControls(true);
  paintStructure(response);
  get("structure-toggle").disabled = false;
  get("inspector-toggle").disabled = false;
  if (response.scope_truncated && response.module_total != null) {
    notice.textContent = response.module_total.toLocaleString() + " indexed modules · Search this scope to find any module.";
  } else if (response.module_overview && response.module_total != null) {
    notice.textContent = response.module_total.toLocaleString() + " indexed modules · Open a group to explore its contents.";
  } else if (layout.edges.length > 16 || response.edges_truncated) {
    notice.textContent = "Select an element to highlight its dependencies.";
  }
  focusMap(null);
  zoomMap(0);
  get("previous").hidden = (pageTrails.get(response.parent)?.length ?? 0) <= 1;
  get("more").hidden = !response.next_cursor;
}

export function bindMap() {
  bindMapLayouts();
  mapView.treeOpen = matchMedia("(min-width: 1100px)").matches;
  structure(mapView.treeOpen);
  inspector(false);
  get("structure-toggle").addEventListener("click", () => {
    mapView.treeOpen = get("structure-pane").hidden;
    structure(mapView.treeOpen);
    zoomMap(0);
  });
  get("inspector-toggle").addEventListener("click", () => {
    inspector(details.hidden);
    if (!details.hidden) details.focus({ preventScroll: true });
    zoomMap(0);
  });
  for (const mode of (["components", "modules"] as const)) {
    get("map-" + mode).addEventListener("click", () => {
      if (mapView.mode === mode) return;
      mapView.mode = mode;
      pageTrails.delete(state.ancestors.at(-1)?.id ?? system.id);
      showScope(state.ancestors).catch(showError);
    });
  }
  cards.addEventListener("click", (event) => {
    if (event.target instanceof Element && !event.target.closest("button, a") && event.target.closest(".map-plane")) {
      state.selected = null;
      for (const node of cards.querySelectorAll("[data-element]")) node.setAttribute("aria-pressed", "false");
      focusMap(null);
      inspector(false);
    }
  });
}
