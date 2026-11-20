"use strict";
const get = (id) => document.getElementById(id);
const canvas = get("canvas");
const viewport = get("viewport");
const cards = get("cards");
const details = get("details");
const notice = get("notice");
const system = { id: "system", name: "System", kind: "system" };
const state = {
  ancestors: [system], items: [], cursor: null, selected: null, edges: [], request: 0,
  hops: [], storyIndex: -1, zoom: 1,
};
const pageTrails = new Map();
const known = new Map([[system.id, system]]);
function element(tag, text, className) {
  const result = document.createElement(tag);
  result.textContent = text;
  if (className) result.className = className;
  return result;
}

function button(text, action, className) {
  const result = element("button", text, className);
  result.type = "button";
  result.addEventListener("click", () => Promise.resolve(action()).catch(showError));
  return result;
}

function showError(error) {
  notice.textContent = error.message;
}

async function api(operation, args = {}) {
  const response = await fetch("/api/v1/" + operation + "?" + new URLSearchParams(args));
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function updateOverview({ coverage }) {
  const displayNames = { python: "Python", rust: "Rust", dart: "Dart", typescript: "TypeScript", javascript: "JavaScript" };
  const languages = new Set((coverage.parts ?? []).map((part) => part.language).filter(Boolean));
  const facts = [...languages].sort().map((language) => displayNames[language] ?? language);
  const summary = [facts.join(", ")].filter(Boolean);
  for (const [key, noun] of [["components", coverage.observed_only ? "layout group" : "component"], ["modules", "module"]]) {
    const count = coverage.total?.[key];
    if (Number.isInteger(count)) summary.push(count.toLocaleString() + " " + noun + (count === 1 ? "" : "s"));
  }
  get("overview").textContent = summary.join(" · ");
  get("native-report").hidden = Boolean(coverage.observed_only);
  if (coverage.observed_only) details.append(element("p", "Observed structure grouped by layout."));
  if (coverage.truncated) details.append(element("p", "The snapshot retains a limited topology."));
  else if (coverage.complete === false) details.append(element("p", "The snapshot covers part of the system."));
  const imports = coverage.external_imports;
  if (imports?.packages.length) {
    const remaining = imports.total - imports.packages.length;
    const names = imports.packages.join(", ") + (remaining ? " · " + remaining.toLocaleString() + " more" : "");
    details.append(element("h3", "Observed external imports"), element("p", names));
  }
}
function breadcrumbs(source = false) {
  const nav = get("breadcrumbs");
  nav.replaceChildren();
  state.ancestors.forEach((item, index) => {
    if (index > 0) nav.append(element("span", "/", "muted"));
    if (index === state.ancestors.length - 1 && !source) {
      const current = element("strong", item.name);
      current.setAttribute("aria-current", "page");
      nav.append(current);
    } else {
      nav.append(button(item.name, () => showScope(state.ancestors.slice(0, index + 1))));
    }
  });
  if (source) {
    nav.append(element("span", "/", "muted"));
    nav.append(element("strong", "Source"));
  }
}
function label(id) {
  return known.get(id)?.name ?? id;
}
function relationLabel(edge) {
  const kind = { requires: "Requires", import: "Import", interface: "Interface", call: "Call" }[edge.kind] ?? edge.kind;
  if (edge.kind === "call" && edge.resolution !== "resolved") return kind + " · UNKNOWN";
  const status = { unresolved: " · UNKNOWN", open: " · UNKNOWN", declared: " · Declared", candidate: " · Candidate" }[edge.resolution] ?? "";
  return kind + status;
}
function drawArrows() {
  const layer = get("arrows").querySelector("g");
  layer.replaceChildren();
  const rect = canvas.getBoundingClientRect();
  const scale = rect.width / canvas.offsetWidth || 1;
  const nodeRects = new Map(Array.from(cards.querySelectorAll("[data-element]"), (card) =>
    [card.dataset.element, card.getBoundingClientRect()]));
  for (const edge of state.edges) {
    const a = nodeRects.get(edge.source);
    const b = nodeRects.get(edge.target);
    if (!a || !b || a === b) continue;
    const sameRow = Math.abs(a.top - b.top) < 5;
    const right = a.left < b.left;
    const down = a.top < b.top;
    const blocked = sameRow && [...nodeRects.values()].some((box) =>
      Math.abs(a.top - box.top) < 5 &&
      box.left > Math.min(a.left, b.left) && box.left < Math.max(a.left, b.left));
    const adjacent = sameRow && !blocked;
    const x1 = ((adjacent ? (right ? a.right : a.left) : (a.left + a.right) / 2) - rect.left) / scale;
    const x2 = ((adjacent ? (right ? b.left : b.right) : (b.left + b.right) / 2) - rect.left) / scale;
    const y1 = ((sameRow ? (blocked ? a.top : (a.top + a.bottom) / 2) : (down ? a.bottom : a.top)) - rect.top) / scale;
    const y2 = ((sameRow ? (blocked ? b.top : (b.top + b.bottom) / 2) : (down ? b.top : b.bottom)) - rect.top) / scale;
    const midY = blocked ? Math.min(y1, y2) - 12 : (y1 + y2) / 2;
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    let route = `M ${x1} ${y1} C ${x1} ${midY} ${x2} ${midY} ${x2} ${y2}`;
    if (adjacent) route = `M ${x1} ${y1} L ${x2} ${y2}`;
    if (blocked) route = `M ${x1} ${y1} V ${midY} H ${x2} V ${y2}`;
    path.setAttribute("d", route);
    if (["declared", "candidate"].includes(edge.resolution)) path.classList.add("declared");
    if (["unresolved", "open"].includes(edge.resolution) || (edge.kind === "call" && edge.resolution !== "resolved")) path.classList.add("unknown");
    path.setAttribute("marker-end", "url(#arrow)");
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = label(edge.source) + " → " + label(edge.target ?? "Unresolved target") + " · " + relationLabel(edge);
    path.append(title);
    const hit = path.cloneNode(true);
    hit.classList.add("edge-hit");
    hit.removeAttribute("marker-end");
    hit.addEventListener("click", () => showEvidence(edge).catch(showError));
    layer.append(path, hit);
  }
}

async function readEdges() {
  const displayed = state.items;
  const visible = new Set(displayed.map((item) => item.id));
  const edges = new Map();
  const replies = await Promise.all(displayed.map((item) =>
    api("relations", { element: item.id, direction: "out", limit: 80 })));
  if (displayed !== state.items) return;
  for (const reply of replies) {
    for (const edge of reply.items) if (visible.has(edge.target)) edges.set(edge.id, edge);
  }
  state.edges = [...edges.values()];
  drawArrows();
  if (replies.some((reply) => reply.next_cursor)) {
    notice.textContent = "Some dependencies exceed the canvas limit. Select an element to browse its connections.";
  }
}

function selectionHeading(title, kind) {
  details.replaceChildren(element("p", kind, "meta"), element("h2", title));
}

async function showScope(ancestors, query = null) {
  const request = ++state.request;
  stopStoryPlayback();
  setStoryLink(null);
  get("story-controls").hidden = true;
  get("view-title").textContent = "Architecture whiteboard";
  if (query || state.search) pageTrails.clear();
  const active = new Set(ancestors.map((item) => item.id));
  for (const id of pageTrails.keys()) if (!active.has(id)) pageTrails.delete(id);
  state.ancestors = ancestors;
  state.selected = null;
  state.items = [];
  state.edges = [];
  state.cursor = null;
  state.search = query;
  viewport.scrollTo(0, 0);
  notice.textContent = "";
  const current = ancestors.at(-1);
  setMapControls(true, mapScope(current, query));
  breadcrumbs();
  get("map").setAttribute("aria-pressed", "true");
  get("story").setAttribute("aria-pressed", "false");
  selectionHeading(query ? "Search results" : current.name, query ? "Search" : current.kind);
  details.append(element("p", "Select an element or open it with Enter or a double-click."));
  if (current.kind === "class") {
    const coverage = current.member_coverage ?? {};
    for (const [kind, label] of [["property", "Properties"], ["method", "Methods"]]) {
      const status = coverage[kind] ?? (current.members_complete ? "complete" : "unknown");
      details.append(element("p", label + " · " + status + " coverage", "meta"));
    }
  }
  if (current.source) {
    details.append(button("Open source", () => showSource(current.source), "detail-btn"));
  }
  const trail = pageTrails.get(current.id) ?? [""];
  pageTrails.set(current.id, trail);
  cards.replaceChildren(element("p", "Loading elements…"));
  drawArrows();
  get("previous").hidden = get("more").hidden = true;
  const cursor = trail.at(-1);
  const useMap = mapScope(current, query);
  const response = await (useMap ? mapPage(current, cursor)
    : api(query ? "search" : "children", { ...(query ? { text: query } : { parent: current.id }), limit: 12, cursor }));
  if (request !== state.request) return;
  if (current.id === "system" && !query) updateOverview(response);
  state.items = response.items;
  state.cursor = response.next_cursor;
  if (useMap) return showMapResponse(response, request);
  setMapTree(current, response, query);
  paintCards();
  await readEdges();
}
async function open(item) {
  if (canOpenScope(item)) {
    await showScope(mapParents(item));
  } else if (item.source) {
    await showSource(item.source);
  }
}
async function select(item) {
  const request = ++state.request;
  state.selected = item.id;
  inspector(true);
  focusMap(item.id);
  for (const card of cards.querySelectorAll("[data-element]")) {
    card.setAttribute("aria-pressed", String(card.dataset.element === item.id));
  }
  selectionHeading(item.name, item.kind);
  if (item.path) details.append(element("p", item.path, "meta"));
  const unresolved = unknownCalls(item);
  if (unresolved) details.append(unresolved);
  if (canOpenScope(item)) {
    details.append(button("Open " + item.kind, () => open(item), "detail-btn"));
  }
  if (item.source) details.append(button("Open source", () => showSource(item.source), "detail-btn"));
  for (const responsibility of item.responsibilities ?? []) {
    details.append(element("p", responsibility));
  }
  details.append(storyChat(null, item.id), mapConnections(item.id), element("h3", "Connections"));
  async function load(cursor = "") {
    const result = await api("relations", { element: item.id, limit: 30, cursor });
    if (state.request !== request) return;
    for (const edge of result.items) {
      details.append(button(label(edge.source) + " → " + label(edge.target ?? "Unresolved target") + " · " +
        relationLabel(edge), () => showEvidence(edge), edge.kind === "call" && edge.resolution !== "resolved" ? "detail-btn unknown" : "detail-btn"));
    }
    if (!cursor && !result.items.length) details.append(element("p", "No indexed connections."));
    if (result.next_cursor) {
      const more = button("More connections", async () => {
        more.remove();
        await load(result.next_cursor);
      }, "detail-btn");
      details.append(more);
    }
  }
  await load();
}
async function showEvidence(edge) {
  const request = ++state.request;
  const { items, relation } = await api("evidence", { relation: edge.id });
  if (request !== state.request) return;
  inspector(true);
  selectionHeading(relationDirection(edge), relationLabel(relation));
  details.append(element("h3", edge.aggregate ? "Example call from " + edge.count + " recorded calls" : "Dependency evidence"));
  if (relation.title) details.append(element("p", relation.title));
  if (relation.expression) details.append(element("p", relation.expression, "meta"));
  if (relation.reason) details.append(element("p", relation.reason, "unknown"));
  if (relation.kind === "call") {
    details.append(button("Follow call in Story", () => {
      const existing = state.hops.findIndex((step) => step.id === relation.id);
      return showStory(relation.id, existing);
    }, "detail-btn"));
  }
  if (relation.rationale) details.append(element("p", relation.rationale));
  if (relation.schema) details.append(element("p", relation.schema, "meta"));
  if (relation.evidence_total !== undefined) {
    details.append(element("p", items.length + " of " + relation.evidence_total + " source locations"));
  }
  if (!items.length) details.append(element("p", "This relation has no indexed source location."));
  for (const item of items) {
    details.append(button(item.path + ":" + item.line, () => showSource(item.reference), "detail-btn"));
  }
  details.focus({ preventScroll: true });
}
async function showSource(reference, start) {
  const request = ++state.request;
  stopStoryPlayback();
  const args = { reference, limit: 32 };
  if (start) args.start = start;
  const result = await api("source", args);
  if (request !== state.request) return;
  state.edges = [];
  inspector(true);
  drawArrows();
  const source = element("article", "", "source");
  source.append(element("h2", result.path));
  const code = element("pre", "");
  for (const [index, line] of result.lines.entries()) {
    const number = result.start + index;
    code.append(element("div", String(number).padStart(4) + "  " + line,
      number === result.line ? "marked" : ""));
  }
  source.append(code);
  if (result.start > 1) {
    source.append(button("Previous lines", () => showSource(reference, Math.max(1, result.start - 32))));
  }
  if (result.lines.length === 32) {
    source.append(button("Next lines", () => showSource(reference, result.start + 32)));
  }
  cards.replaceChildren(source);
  get("previous").hidden = get("more").hidden = true;
  selectionHeading(result.path, "Source");
  details.append(element("p", "Lines from the indexed source reference."));
  const step = state.hops[state.storyIndex];
  if (step && get("story").getAttribute("aria-pressed") === "true") {
    get("story-controls").hidden = true;
    const back = reopenStory;
    details.append(button("Back to Story", back, "detail-btn"));
    get("breadcrumbs").replaceChildren(button("Story", back),
      element("span", "/", "muted"), element("strong", "Source"));
  } else {
    details.append(button("Back to scope", () => showScope(state.ancestors), "detail-btn"));
    breadcrumbs(true);
  }
}

const scales = [75, 100, 125, 150];

function zoom(delta, whole = false) {
  if (zoomMap(delta, whole)) return;
  state.zoom = delta ? Math.max(0, Math.min(scales.length - 1, state.zoom + delta)) : 1;
  canvas.dataset.zoom = String(scales[state.zoom]);
  get("zoom-level").textContent = scales[state.zoom] + "%";
  get("zoom-out").disabled = state.zoom === 0;
  get("zoom-in").disabled = state.zoom === scales.length - 1;
  if (!delta) viewport.scrollTo(0, 0);
  drawArrows();
}

get("zoom-out").addEventListener("click", () => zoom(-1));
get("zoom-in").addEventListener("click", () => zoom(1));
get("zoom-fit").addEventListener("click", () => zoom(0, true));
viewport.addEventListener("keydown", (event) => {
  if (event.target !== viewport) return;
  if (event.key === "Escape" && state.ancestors.length > 1) {
    showScope(state.ancestors.slice(0, -1)).catch(showError);
    return;
  }
  const keys = { "+": 1, "=": 1, "-": -1, "0": 0 };
  if (!(event.key in keys)) return;
  event.preventDefault();
  zoom(keys[event.key]);
});

let drag;
viewport.addEventListener("pointerdown", (event) => {
  if (event.pointerType !== "mouse" || event.button !== 0 ||
      event.target.closest("button,a,pre,.edge-hit")) return;
  drag = [event.clientX + viewport.scrollLeft, event.clientY + viewport.scrollTop];
  viewport.dataset.panning = "";
  viewport.setPointerCapture(event.pointerId);
});
viewport.addEventListener("pointermove", (event) => {
  if (drag) viewport.scrollTo(drag[0] - event.clientX, drag[1] - event.clientY);
});
viewport.addEventListener("lostpointercapture", () => {
  drag = null;
  delete viewport.dataset.panning;
});

get("map").addEventListener("click", () => showScope([system]).catch(showError));
get("search-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const query = get("search").value.trim();
  if (query) showScope([system], query).catch(showError);
});
async function changePage(forward) {
  const scope = state.ancestors.at(-1).id;
  const trail = pageTrails.get(scope);
  if (!trail || (forward ? !state.cursor : trail.length < 2)) return;
  const next = forward ? [...trail, state.cursor] : trail.slice(0, -1);
  const request = ++state.request;
  const current = state.ancestors.at(-1);
  const useMap = mapScope(current, state.search);
  const cursor = next.at(-1);
  const args = state.search ? { text: state.search } : { parent: scope };
  const result = await (useMap ? mapPage(current, cursor)
    : api(state.search ? "search" : "children", { ...args, cursor, limit: 12 }));
  if (request !== state.request) return;
  pageTrails.set(scope, next);
  state.items = result.items;
  state.cursor = result.next_cursor;
  if (useMap) return showMapResponse(result, request);
  setMapTree(current, result, state.search);
  paintCards();
  viewport.scrollTo(0, 0);
  await readEdges();
}
get("more").addEventListener("click", () => changePage(true).catch(showError));
get("previous").addEventListener("click", () => changePage(false).catch(showError));
get("theme").addEventListener("click", () => {
  const dark = document.documentElement.dataset.theme === "dark";
  document.documentElement.dataset.theme = dark ? "light" : "dark";
  get("theme").textContent = dark ? "☾" : "☼";
  get("theme").setAttribute("aria-label", "Switch to " + (dark ? "dark" : "light") + " theme");
});
bindStory();
bindMap();
new ResizeObserver(drawArrows).observe(canvas);
const initialStory = new URLSearchParams(location.search).get("story");
(initialStory ? loadStory(initialStory) : showScope([system])).catch(showError);
