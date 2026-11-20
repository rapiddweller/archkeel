"use strict";

function showError(error, retry) {
  notice.replaceChildren(element("span", error.message || "The request failed."));
  if (retry) notice.append(" ", button("Retry", retry));
}

async function showScope(ancestors, query = null) {
  const request = ++state.request;
  stopStoryPlayback();
  const current = ancestors.at(-1);
  const trail = query || state.search ? [""] : (pageTrails.get(current.id) ?? [""]);
  const cursor = trail.at(-1);
  const useMap = mapScope(current, query);
  let response, layout;
  try {
    response = await (useMap ? mapPage(current, cursor)
      : api(query ? "search" : "children", { ...(query ? mapSearchArgs(current.id, query) : { parent: current.id }), limit: 12, cursor }));
    if (request !== state.request) return;
    if (useMap && response.items.length) layout = await layoutMap(response);
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
  state.ancestors = ancestors;
  state.selected = null;
  state.items = response.items;
  state.edges = [];
  state.cursor = response.next_cursor;
  state.search = query;
  viewport.scrollTo(0, 0);
  notice.textContent = "";
  setMapControls(true, useMap);
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
  if (current.source) details.append(button("Open source", () => showSource(current.source), "detail-btn"));
  pageTrails.set(current.id, trail);
  get("previous").hidden = get("more").hidden = true;
  if (current.id === "system" && !query) updateOverview(response);
  if (useMap) return showMapResponse(response, request, layout);
  setMapTree(current, response, query);
  paintCards();
  try { await readEdges(); }
  catch (error) { if (request === state.request) showError(error, () => showScope(ancestors, query)); }
}
