import { api, type Page } from "./studio-api.js";
import type { MapResponse, StudioItem } from "./studio-model.js";
import { state, pageTrails } from "./studio-state.js";
import { get, details, element, viewport, notice, button, showError } from "./studio-dom.js";
import { breadcrumbs, readEdges, selectionHeading, showSource, updateOverview } from "./explorer.js";
import { mapScope, mapSearchArgs, setStoryLink, setMapControls, showMapResponse, setMapTree } from "./explorer-map.js";
import { layoutMap, mapPage } from "./explorer-map-layout.js";
import { itemKind, paintCards } from "./explorer-uml.js";
import { stopStoryPlayback } from "./explorer-story.js";
export { showError } from "./studio-dom.js";

function isMap(response: Page<StudioItem> | MapResponse): response is MapResponse {
  return "groups" in response && "edges" in response;
}

export async function showScope(ancestors: StudioItem[], query: string | null = null) {
  const request = ++state.request;
  stopStoryPlayback();
  const current = ancestors.at(-1)!;
  const trail = query || state.search ? [""] : (pageTrails.get(current.id) ?? [""]);
  const cursor = trail.at(-1) ?? "";
  const useMap = mapScope(current, query);
  let response, layout;
  try {
    response = await (useMap ? mapPage(current, cursor)
      : api<Page<StudioItem>>(query ? "search" : "children", { ...(query ? mapSearchArgs(current.id, query) : { parent: current.id }), limit: 12, cursor }));
    if (request !== state.request) return;
    if (isMap(response) && response.items.length) layout = await layoutMap(response);
    if (request !== state.request) return;
  } catch (error) {
    if (request === state.request) showError(error, () => showScope(ancestors, query));
    return;
  }
  setStoryLink(null);
  get("story-controls").hidden = true;
  get("view-title").textContent = "Architecture whiteboard";
  if (query || state.search) pageTrails.clear();
  const active = new Set(ancestors.map((item) => item.id));
  for (const id of pageTrails.keys()) if (!active.has(id)) pageTrails.delete(id);
  const selection = current.id === state.ancestors.at(-1)?.id && query === state.search ? state.selected : null;
  state.ancestors = ancestors;
  state.selected = selection;
  state.items = response.items;
  state.edges = [];
  state.cursor = response.next_cursor;
  state.search = query;
  viewport.scrollTo(0, 0);
  notice.textContent = "";
  setMapControls(true);
  breadcrumbs();
  get("map").setAttribute("aria-pressed", "true");
  get("story").setAttribute("aria-pressed", "false");
  const kind = itemKind(current, response.coverage?.observed_only);
  const group = ["component", "layer", "directory", "file_group"].includes(current.kind);
  selectionHeading(query ? "Search results" : current.name, query ? "Search" : group ? kind + " · includes descendants" : kind);
  details.append(element("p", "Select an element or open it with Enter or a double-click."));
  if (current.kind === "class") {
    const coverage = current.member_coverage ?? {};
    for (const [kind, label] of [["property", "Properties"], ["method", "Methods"]]) {
      const status = coverage[kind] ?? (current.members_complete ? "complete" : "unknown");
      details.append(element("p", label + " · " + status + " coverage", "meta"));
    }
  }
  if (current.source) details.append(button("Open source", () => showSource(current.source!), "detail-btn"));
  pageTrails.set(current.id, trail);
  get("previous").hidden = get("more").hidden = true;
  if (current.id === "system" && !query) updateOverview(response);
  if (isMap(response)) return showMapResponse(response, request, layout);
  setMapTree(current, response, query);
  paintCards();
  try { await readEdges(); }
  catch (error) { if (request === state.request) showError(error, () => showScope(ancestors, query)); }
}

export async function changePage(forward: boolean) {
  const scope = state.ancestors.at(-1)!.id;
  const trail = pageTrails.get(scope);
  if (!trail || (forward ? !state.cursor : trail.length < 2)) return;
  const next = forward ? [...trail, state.cursor!] : trail.slice(0, -1);
  const request = ++state.request;
  const current = state.ancestors.at(-1)!;
  const useMap = mapScope(current, state.search);
  const cursor = next.at(-1) ?? "";
  const args = state.search ? mapSearchArgs(scope, state.search) : { parent: scope };
  const result = await (useMap ? mapPage(current, cursor)
    : api<Page<StudioItem>>(state.search ? "search" : "children", { ...args, cursor, limit: 12 }));
  if (request !== state.request) return;
  pageTrails.set(scope, next);
  state.items = result.items;
  state.cursor = result.next_cursor;
  if (isMap(result)) return showMapResponse(result, request);
  setMapTree(current, result, state.search);
  paintCards();
  viewport.scrollTo(0, 0);
  await readEdges();
}
