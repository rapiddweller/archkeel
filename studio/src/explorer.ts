import { api, type Page } from "./studio-api.js";
import type { StudioCoverage, StudioItem, StudioEdge } from "./studio-model.js";
import { state, system, known } from "./studio-state.js";
import { breakPath, get, element, button, canvas, cards, details, viewport, notice, showError } from "./studio-dom.js";
import { showScope, changePage } from "./explorer-navigation.js";
import { bindMap, derivedMapGroup, focusMap, mapParents, mapSearchArgs, mapView, loadMapFocus, appendSelectionNotes, relationDirection, unknownCalls } from "./explorer-map.js";
import { inspector, zoomMap } from "./explorer-map-layout.js";
import { canOpenScope, itemKind } from "./explorer-uml.js";
import { bindStory, reopenStory, stopStoryPlayback } from "./explorer-story.js";
import { loadStory, showStory } from "./explorer-story-loading.js";

interface Evidence {
  items: {path: string; line: number; reference: string; role?: string}[];
  relation: StudioEdge;
  next_cursor: string | null;
  total: number;
  evidence_total: number;
  evidence_truncated: boolean;
}
interface Source {
  path: string; lines: string[]; start: number; line: number;
}

export function updateOverview({ coverage = {} }: {coverage?: StudioCoverage}) {
  const displayNames: Record<string, string> = { python: "Python", rust: "Rust", dart: "Dart", typescript: "TypeScript", javascript: "JavaScript" };
  const languages = new Set((coverage.parts ?? []).flatMap((part) => part.language ? [part.language] : []).filter(Boolean));
  const facts = [...languages].sort().map((language) => displayNames[language] ?? language);
  const summary = [facts.join(", ")].filter(Boolean);
  for (const [key, noun] of [["components", coverage.observed_only ? "layout group" : "component"], ["modules", "module"]]) {
    const count = coverage.total?.[key];
    if (typeof count === "number") summary.push(count.toLocaleString() + " " + noun + (count === 1 ? "" : "s"));
  }
  get("overview").textContent = summary.join(" · ");
  get("native-report").hidden = Boolean(coverage.observed_only);
  if (coverage.observed_only) details.append(element("p", "Observed structure grouped by layout."));
  if (coverage.truncated) details.append(element("p", "The snapshot retains a limited topology."));
  else if (coverage.complete === false) details.append(element("p", "The snapshot covers part of the system."));
  for (const part of coverage.parts ?? []) {
    if (part.files_indexed == null) continue;
    const counts = [part.files_indexed + " indexed files"];
    if (part.files_with_symbols != null) counts.push(part.files_with_symbols + " with symbol records");
    if (part.files_with_calls != null) counts.push(part.files_with_calls + " with call records");
    details.append(element("p", (part.part || part.language || "Scan") + " · " + counts.join(" · ")));
  }
  const imports = coverage.external_imports;
  if (imports?.packages.length) {
    const remaining = imports.total - imports.packages.length;
    const names = imports.packages.join(", ") + (remaining ? " · " + remaining.toLocaleString() + " more" : "");
    details.append(element("h3", "Observed external imports"), element("p", names));
  }
}
export function breadcrumbs(source = false) {
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
export function label(id: string) {
  return known.get(id)?.name ?? id;
}
export function relationLabel(edge: StudioEdge) {
  const kinds: Record<string, string> = { requires: "Requires", import: "Import", import_site: "Import", interface: "Interface", call: "Call", source_call: "Call target" };
  const kind = kinds[edge.kind] ?? edge.kind;
  if (edge.kind === "call" && edge.resolution !== "resolved") return kind + " · UNKNOWN";
  const statuses: Record<string, string> = { unresolved: " · UNKNOWN", open: " · UNKNOWN", declared: " · Declared", candidate: " · Candidate" };
  const status = statuses[edge.resolution] ?? "";
  return kind + status;
}
export function drawArrows() {
  const layer = get("arrows").querySelector("g")!;
  layer.replaceChildren();
  const rect = canvas.getBoundingClientRect();
  const scale = rect.width / canvas.offsetWidth || 1;
  const nodeRects = new Map(Array.from(cards.querySelectorAll<HTMLElement>("[data-element]"), (card) =>
    [card.dataset.element, card.getBoundingClientRect()]));
  for (const edge of state.edges) {
    const a = nodeRects.get(edge.source);
    const b = edge.target ? nodeRects.get(edge.target) : undefined;
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
    const hit = document.createElementNS("http://www.w3.org/2000/svg", "path");
    hit.setAttribute("d", route);
    hit.classList.add("edge-hit");

    hit.addEventListener("click", () => showEvidence(edge).catch(showError));
    layer.append(path, hit);
  }
}

export async function readEdges() {
  const displayed = state.items;
  const visible = new Set(displayed.map((item) => item.id));
  const edges = new Map<string, StudioEdge>();
  const replies = await Promise.all(displayed.map((item) =>
    api<Page<StudioEdge>>("relations", { element: item.id, direction: "out", limit: 80 })));
  if (displayed !== state.items) return;
  for (const reply of replies) {
    for (const edge of reply.items) if (edge.target && visible.has(edge.target)) edges.set(edge.id, edge);
  }
  state.edges = [...edges.values()];
  drawArrows();
  if (replies.some((reply) => reply.next_cursor)) {
    notice.textContent = "Some dependencies exceed the canvas limit. Select an element to browse its connections.";
  }
}

export function selectionHeading(title: string, kind: string) {
  const heading = element("h2", "");
  breakPath(heading, title);
  details.replaceChildren(element("p", kind, "meta"), heading);
}


export async function open(item: StudioItem) {
  if (canOpenScope(item)) {
    await showScope(mapParents(item));
  } else if (item.source) {
    await showSource(item.source);
  }
}
export async function select(item: StudioItem) {
  const request = ++state.request;
  state.selected = item.id;
  inspector(true);
  await loadMapFocus(item);
  if (request !== state.request) return;
  focusMap(item.id);
  for (const card of cards.querySelectorAll<HTMLElement>("[data-element]")) {
    card.setAttribute("aria-pressed", String(card.dataset.element === item.id));
  }
  const group = ["component", "layer", "directory", "file_group"].includes(item.kind);
  const kind = itemKind(item, mapView.response?.coverage?.observed_only);
  selectionHeading(item.name, group ? kind + " · includes descendants" : kind);
  const coverage = mapView.response?.coverage;
  const coverageNote = coverage?.complete === true && !coverage.truncated
    ? "Snapshot coverage complete." : "Snapshot coverage incomplete or unknown; connections may be missing.";
  details.append(element("p", coverageNote, "meta"));
  if (mapView.response?.edges_truncated) details.append(element("p", "This map omits some connections.", "meta"));
  if (item.path) details.append(breakPath(element("p", "", "meta"), item.path));
  const unresolved = unknownCalls(item);
  if (unresolved) details.append(unresolved, element("p", unresolved.title, "meta"));
  else if (Number.isInteger(item.recorded_calls)) details.append(element("p", item.recorded_calls ? item.recorded_calls.toLocaleString() + " calls have a resolved target." : "No call sites recorded in this scope.", "meta"));
  if (canOpenScope(item)) {
    details.append(button("Open " + item.kind, () => open(item), "detail-btn"));
  }
  if (item.source) details.append(button("Open source", () => showSource(item.source!), "detail-btn"));
  appendSelectionNotes(item);
  if (derivedMapGroup(item)) return;
  async function load(cursor = "") {
    const result = await api<Page<StudioEdge>>("relations", { element: item.id, limit: 30, cursor });
    if (state.request !== request) return;
    for (const edge of result.items) {
      const endpoints = relationDirection(edge);
      const text = endpoints + " · " + relationLabel(edge);
      const link = button(text, () => showEvidence(edge), edge.kind === "call" && edge.resolution !== "resolved" ? "detail-btn unknown" : "detail-btn");
      details.append(breakPath(link, text));
    }
    if (!cursor && !result.items.length) details.append(element("p", "No indexed connections."));
    if (result.next_cursor) {
      const more = button("More connections", async () => {
        more.remove();
        await load(result.next_cursor!);
      }, "detail-btn");
      details.append(more);
    }
  }
  await load();
}
export async function showAggregates(edges: StudioEdge[], title: string) {
  const request = ++state.request;
  inspector(true);
  selectionHeading(title, "Relations");
  for (const edge of edges) {
    if (!edge.aggregate_id) {
      const text = relationDirection(edge) + " · " + relationLabel(edge);
      const link = button(text, () => showEvidence(edge), "detail-btn");
      details.append(breakPath(link, text));
      continue;
    }
    let cursor: string | null = "";
    do {
      const result: Page<StudioEdge> = await api<Page<StudioEdge>>("relations", { aggregate: edge.aggregate_id, limit: 30, cursor });
      if (request !== state.request) return;
      if (!cursor && result.total !== undefined && result.count !== undefined && result.total !== result.count) {
        details.append(element("p", result.total + " relations · " + result.count + (edge.kind === "import" ? " recorded imports" : " recorded sites"), "meta"));
      }
      for (const relation of result.items) {
        const text = relationDirection(relation) + " · " + relationLabel(relation);
        const link = button(text, () => showEvidence(relation), "detail-btn");
        details.append(breakPath(link, text));
      }
      cursor = result.next_cursor;
    } while (cursor);
  }
  details.focus({ preventScroll: true });
}
export async function showEvidence(edge: StudioEdge) {
  if (edge.aggregate && edge.aggregate_id) return showAggregates([edge], relationDirection(edge));
  const request = ++state.request;
  inspector(true);
  const result = await api<Evidence>("evidence", { relation: edge.id, limit: 30 });
  if (request !== state.request) return;
  const relation = result.relation;
  selectionHeading(relation.declaration ? (relation.expression ?? relation.declaration) : relationDirection(edge), relationLabel(relation));
  details.append(element("h3", relation.declaration ? "Possible declaration" : "Dependency evidence"));
  if (relation.title) details.append(element("p", relation.title));
  if (relation.declaration) details.append(breakPath(element("p", "", "meta"), relation.declaration));
  else if (relation.expression) details.append(element("p", relation.expression, "meta"));
  if (relation.reason) details.append(element("p", relation.reason, "unknown"));
  if (relation.kind === "call") {
    details.append(button("Follow call in Story", () => {
      const existing = state.hops.findIndex((step) => "id" in step && step.id === relation.id);
      return showStory(relation.id, existing);
    }, "detail-btn"));
  }
  if (relation.rationale) details.append(element("p", relation.rationale));
  if (relation.schema) details.append(element("p", relation.schema, "meta"));
  if (!relation.declaration && result.total !== undefined) details.append(element("p", result.total + " indexed source locations"));
  if (result.evidence_truncated) details.append(element("p", "Some source locations were not retained.", "unknown"));
  async function appendEvidence(page: Evidence) {
    if (!page.items.length && !page.next_cursor) details.append(element("p", "This relation has no indexed source location."));
    for (const item of page.items) {
      const role = item.role === "call_site" ? "Call site · " : item.role === "declaration" ? "Declaration · " : "";
      const text = role + item.path + ":" + item.line;
      const link = button(text, () => showSource(item.reference), "detail-btn");
      details.append(breakPath(link, text));
    }
    if (page.next_cursor) {
      const more = button("More source locations", async () => {
        const next = await api<Evidence>("evidence", { relation: edge.id, limit: 30, cursor: page.next_cursor });
        if (request !== state.request) return;
        more.remove();
        await appendEvidence(next);
      }, "detail-btn");
      details.append(more);
    }
  }
  await appendEvidence(result);
  details.focus({ preventScroll: true });
}
export async function showSource(reference: string, start?: number) {
  const request = ++state.request;
  stopStoryPlayback();
  const result = await api<Source>("source", {reference, limit: 32, start});
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
    details.append(button("Back to Story", reopenStory, "detail-btn"));
    get("breadcrumbs").replaceChildren(button("Story", reopenStory),
      element("span", "/", "muted"), element("strong", "Source"));
  } else {
    details.append(button("Back to scope", () => showScope(state.ancestors), "detail-btn"));
    breadcrumbs(true);
  }
}

const scales = [75, 100, 125, 150];

function zoom(delta: number, whole = false) {
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
  const keys: Record<string, number> = { "+": 1, "=": 1, "-": -1, "0": 0 };
  if (!(event.key in keys)) return;
  event.preventDefault();
  zoom(keys[event.key]);
});

let drag: [number, number] | null = null;
viewport.addEventListener("pointerdown", (event) => {
  if (event.pointerType !== "mouse" || event.button !== 0 ||
      (event.target instanceof Element && event.target.closest("button,a,pre,.edge-hit"))) return;
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
  if (query) showScope(mapSearchArgs(state.ancestors.at(-1)!.id, query).parent ? state.ancestors : [system], query).catch(showError);
});
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
