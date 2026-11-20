"use strict";

const mapView = { mode: "components", response: null, scene: null, treeOpen: false };
const mapCardWidth = 224;

function mapScope(item, query) {
  return !query && ["system", "component"].includes(item.kind);
}

function inspector(open) {
  details.hidden = !open;
  get("inspector-toggle").setAttribute("aria-pressed", String(open));
}

function structure(open) {
  get("structure-pane").hidden = !open;
  get("structure-toggle").setAttribute("aria-pressed", String(open));
}

function setStoryLink(id) {
  const url = new URL(location.href);
  if (id) url.searchParams.set("story", id);
  else url.searchParams.delete("story");
  if (url.href !== location.href) history.replaceState(null, "", url);
}

function setMapControls(active, overview = false) {
  get("map-modes").hidden = !overview;
  get("map-components").setAttribute("aria-pressed", String(mapView.mode === "components"));
  get("map-modules").setAttribute("aria-pressed", String(mapView.mode === "modules"));
  if (!active) {
    structure(false);
    inspector(true);
  } else structure(mapView.treeOpen);
}

function setMapTree(current, response, query) {
  if (query) structure(false);
  get("structure-toggle").disabled = Boolean(query);
  paintStructure({ parent: current.id, items: query ? [] : response.items });
}

function mapParents(item) {
  const current = state.ancestors.at(-1).id;
  const ancestors = [];
  let owner = known.get(item.parent);
  while (owner && owner.id !== current && !state.ancestors.includes(owner) && !ancestors.includes(owner)) {
    ancestors.unshift(owner);
    owner = known.get(owner.parent);
  }
  return [...state.ancestors, ...ancestors.filter((node) => node.kind === "component"), item];
}

function mapEdgeName(edge) {
  const name = edge.title ?? relationLabel(edge);
  return edge.count > 1 ? name + " × " + edge.count.toLocaleString() : name;
}

function unknownCalls(item, compact = false) {
  if (!(item.unresolved_calls > 0)) return null;
  const count = item.unresolved_calls.toLocaleString();
  const explanation = count + " calls · UNKNOWN target";
  const badge = element("span", compact ? count + " UNKNOWN" : explanation, "map-unknown");
  badge.title = explanation;
  return badge;
}

function mapSvg(name, attributes, parent) {
  const item = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, value);
  parent.append(item);
  return item;
}

function mapPosition(node, x, y, width, height) {
  node.style.left = x + "px";
  node.style.top = y + "px";
  if (width) node.style.width = width + "px";
  if (height) node.style.height = height + "px";
}

function mapCard(item) {
  const card = umlCard(item);
  const head = card.querySelector(".uml-head");
  if (item.kind === "module" && item.path) {
    head.querySelector(".uml-name").textContent = item.path.split("/").at(-1);
    head.append(element("span", item.path, "map-card-path"));
  }
  const unresolved = unknownCalls(item);
  if (unresolved) head.append(unresolved);
  return card;
}

function paintMapScene(layout, response) {
  const plane = element("section", "", "map-plane");
  plane.setAttribute("aria-label", "Architecture graph");
  mapPosition(plane, 0, 0, layout.width, layout.height);
  const svg = mapSvg("svg", { class: "map-edges", width: layout.width, height: layout.height, "aria-hidden": "true" }, plane);
  const marker = mapSvg("marker", {
    id: "map-arrow", viewBox: "0 0 10 10", refX: "9", refY: "5", markerWidth: "7",
    markerHeight: "7", orient: "auto",
  }, mapSvg("defs", {}, svg));
  mapSvg("path", { d: "M0 0 L10 5 L0 10 Z" }, marker);
  const containers = new Map();
  const ensureContainer = (id) => {
    if (containers.has(id)) return containers.get(id);
    const group = known.get(id);
    const frame = layout.frames["node:" + id];
    const owner = layout.frames["node:" + group.parent];
    const parent = owner ? ensureContainer(group.parent) : plane;
    const section = element("section", "", "map-group " + group.kind);
    section.setAttribute("aria-label", group.name);
    section.dataset.group = id;
    const title = group.kind === "component" ? button("", () => select(group)) : element("span", "");
    title.className = "map-group-title";
    title.title = group.name;
    if (group.kind === "component") {
      title.dataset.element = id;
      title.addEventListener("dblclick", () => open(group).catch(showError));
    }
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
    mapPosition(card, at.x - (parent?.left ?? 0), at.y - (parent?.top ?? 0), size.width, size.height);
    (containers.get(item.parent) ?? plane).append(card);
  }
  cards.replaceChildren(plane);
  return { plane, svg, layout };
}

function paintMapConnections(scene, edges) {
  const { plane, svg, layout } = scene;
  for (const edge of plane.querySelectorAll("[data-map-edge]")) edge.remove();
  const routes = mapRoutes(layout, edges);
  for (const edge of edges) {
    const route = routes.get(edge.id);
    const group = mapSvg("g", { "data-map-edge": edge.id }, svg);
    const uncertain = edge.kind === "call" && edge.resolution !== "resolved";
    const style = uncertain ? "unknown" : edge.kind === "call" ? "map-proven" : edge.resolution;
    mapSvg("path", { d: route.d, class: style, "marker-end": "url(#map-arrow)" }, group);
    const label = button(mapEdgeName(edge), () => showEvidence(edge), "map-edge-label");
    if (uncertain) label.classList.add("map-unknown");
    label.title = known.get(edge.source)?.name + " → " + known.get(edge.target)?.name + " · " + relationLabel(edge);
    label.setAttribute("aria-label", mapEdgeName(edge) + " · " + label.title);
    label.dataset.mapEdge = edge.id;
    const at = layout.labels["label:" + edge.id];
    mapPosition(label, at ? at.x : route.mid[0], at ? at.y : route.mid[1] - 12, at?.width);
    if (!at) label.classList.add("centered");
    plane.append(label);
  }
}
function paintStructure(response) {
  const byParent = new Map();
  for (const item of [...(response.groups ?? []), ...response.items]) {
    if (!byParent.has(item.parent)) byParent.set(item.parent, []);
    byParent.get(item.parent).push(item);
  }
  const makeList = (items) => {
    const list = element("ul", "");
    for (const item of items) {
      const li = element("li", "");
      const nested = byParent.get(item.id);
      const title = item.path?.split("/").at(-1) ?? item.name;
      const action = ["layer", "directory"].includes(item.kind) ? element("span", title)
        : button(title, () => {
          const card = [...cards.querySelectorAll("[data-element]")].find((node) => node.dataset.element === item.id);
          const result = select(item);
          if (card) {
            const box = card.getBoundingClientRect();
            const stage = viewport.getBoundingClientRect();
            const freeWidth = Math.max(200, stage.width - details.clientWidth);
            viewport.scrollBy(box.x - stage.x - (freeWidth - box.width) / 2,
              box.y - stage.y - (stage.height - box.height) / 2);
          }
          return result;
        });
      action.dataset.treeNode = item.id;
      action.title = item.name;
      if (action.tagName === "BUTTON") action.addEventListener("dblclick", () => open(item).catch(showError));
      if (nested?.length) {
        const subtree = element("details", "");
        const head = element("summary", "");
        subtree.open = true;
        head.append(action);
        subtree.append(head, makeList(nested));
        li.append(subtree);
      } else li.append(action);
      list.append(li);
    }
    return list;
  };
  get("structure-tree").replaceChildren(makeList(byParent.get(response.parent) ?? []));
}

function focusedMapEdges(id) {
  return (mapView.scene?.layout.edges ?? []).filter((edge) => edge.source === id || edge.target === id)
    .sort((a, b) => (b.count ?? 1) - (a.count ?? 1)).slice(0, 6);
}

function mapConnections(id) {
  const section = element("section", "");
  const edges = cards.querySelector(".map-plane") ? focusedMapEdges(id) : [];
  if (!edges.length) return section;
  section.append(element("h3", "On this map"));
  for (const edge of edges) {
    const other = label(edge.source === id ? edge.target : edge.source);
    const arrow = edge.source === id ? "→ " : "← ";
    section.append(button(arrow + other + " · " + mapEdgeName(edge), () => showEvidence(edge), "detail-btn"));
  }
  return section;
}

function focusMap(id) {
  const plane = cards.querySelector(".map-plane");
  if (!plane) return;
  const response = mapView.response;
  const scene = mapView.scene;
  const edges = scene.layout.edges;
  const neighbors = new Set(id ? [id] : []);
  const focused = focusedMapEdges(id);
  const scope = (key) => {
    for (let node = known.get(key); node && !neighbors.has(node.id); node = known.get(node.parent)) {
      neighbors.add(node.id);
      if (node.id === response.parent) break;
    }
  };
  if (id) {
    neighbors.delete(id);
    scope(id);
    const below = new Set([id]);
    for (const node of [...(response.groups ?? []), ...response.items]) {
      for (let owner = node; owner && owner.id !== response.parent; owner = known.get(owner.parent)) {
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
  for (const node of plane.querySelectorAll("[data-element], [data-group]")) {
    node.classList.toggle("map-dim", Boolean(id && !neighbors.has(node.dataset.element ?? node.dataset.group)));
  }
  paintMapConnections(scene, edges.length <= 16 && !id ? edges : focused);
  for (const button of get("structure-tree").querySelectorAll("button[data-tree-node]")) {
    button.setAttribute("aria-pressed", String(button.dataset.treeNode === id));
  }
}

function zoomMap(delta, whole = false) {
  const plane = cards.querySelector(".map-plane");
  if (!plane) return false;
  const canvasFit = (viewport.clientWidth - (details.hidden ? 0 : details.clientWidth) - 50) / plane.offsetWidth;
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

function mapPage(current, cursor) {
  return api("map", { parent: current.id, view: mapView.mode, cursor, limit: 36 });
}

async function showMapResponse(response, request) {
  mapView.response = response;
  for (const item of [...(response.groups ?? []), ...response.items]) known.set(item.id, item);
  paintStructure(response);
  if (!response.items.length) return paintCards();
  const layout = await layoutMap(response);
  if (request !== state.request) return;
  mapView.scene = paintMapScene(layout, response);
  get("structure-toggle").disabled = false;
  get("inspector-toggle").disabled = false;
  if (layout.edges.length > 16 || response.edges_truncated) {
    notice.textContent = "Select an element to highlight its dependencies.";
  }
  focusMap(null);
  zoomMap(0);
  get("previous").hidden = (pageTrails.get(response.parent)?.length ?? 0) <= 1;
  get("more").hidden = !response.next_cursor;
}

function bindMap() {
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
  for (const mode of ["components", "modules"]) {
    get("map-" + mode).addEventListener("click", () => {
      if (mapView.mode === mode) return;
      mapView.mode = mode;
      pageTrails.delete(state.ancestors.at(-1).id);
      showScope(state.ancestors).catch(showError);
    });
  }
  cards.addEventListener("click", (event) => {
    if (!event.target.closest("button, a") && event.target.closest(".map-plane")) {
      state.selected = null;
      for (const node of cards.querySelectorAll("[data-element]")) node.setAttribute("aria-pressed", "false");
      focusMap(null);
      inspector(false);
    }
  });
}
