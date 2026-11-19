"use strict";

function endpoint(step, side) {
  const id = step[side];
  const item = known.get(id);
  const name = step[side + "_name"] ?? item?.name;
  const owner = step[side + "_owner"] ?? item?.parent;
  return {
    name: name ?? (id ? "Function identity " + id : "Unresolved target"),
    owner: owner ?? (id ? "Owner unknown" : "Unresolved"),
  };
}

function paintStory() {
  const table = element("table", "", "lanes");
  table.setAttribute("aria-label", "Call sequence by owner");
  const headers = table.createTHead().insertRow();
  const body = table.createTBody();
  const lanes = [...new Set(state.hops.flatMap((step) =>
    [endpoint(step, "source").owner, endpoint(step, "target").owner]))];
  for (const header of ["Step", ...lanes]) {
    const cell = element("th", label(header));
    cell.scope = "col";
    headers.append(cell);
  }
  state.hops.forEach((step, index) => {
    const row = body.insertRow();
    const head = element("th", "");
    head.scope = "row";
    const action = button("Step " + (index + 1) + " · " + step.expression,
      () => showStory(step.id, index));
    action.setAttribute("aria-pressed", String(index === state.storyIndex));
    head.append(action);
    row.append(head);
    const cells = new Map(lanes.map((lane) => [lane, row.insertCell()]));
    const caller = endpoint(step, "source");
    const callee = endpoint(step, "target");
    cells.get(caller.owner).append(element("p", caller.name));
    cells.get(callee.owner).append(
      element("p", step.resolution === "resolved" ? "Resolved call" : "UNKNOWN call", "meta"),
      element("strong", callee.name),
    );
  });
  cards.replaceChildren(table);
}

async function showStory(id, index = -1, follow = false) {
  const request = ++state.request;
  state.items = [];
  state.edges = [];
  state.selected = null;
  const switching = get("story").getAttribute("aria-pressed") !== "true";
  get("map").setAttribute("aria-pressed", "false");
  get("story").setAttribute("aria-pressed", "true");
  get("breadcrumbs").replaceChildren(element("strong", "Story"));
  if (switching || !state.hops.length) {
    cards.replaceChildren();
    viewport.scrollTo(0, 0);
  }
  get("previous").hidden = get("more").hidden = true;
  drawArrows();
  selectionHeading("Follow a call", "Story");
  if (!id) {
    details.append(element("p", "Open a module, select a function, and follow one of its calls."));
    return;
  }
  const result = await api("story", { id });
  if (request !== state.request) return;
  updateCoverage(result);
  if (result.reason) details.append(element("p", result.reason, "unknown"));
  const [step] = result.items;
  if (!step) return;
  if (follow) {
    state.hops = [...state.hops.slice(0, state.storyIndex + 1), step];
    state.storyIndex = state.hops.length - 1;
  } else if (index < 0) {
    state.hops = [step];
    state.storyIndex = 0;
  } else {
    state.storyIndex = index;
  }
  paintStory();
  selectionHeading(step.expression, "Story step " + (state.storyIndex + 1));
  if (step.reason) details.append(element("p", step.reason, "unknown"));
  details.append(button("Inspect call evidence", () => showEvidence(step), "detail-btn"));
  if (!step.target) return;
  const next = await api("relations", { element: step.target, direction: "out", kind: "call", limit: 24 });
  if (request !== state.request) return;
  if (next.items.length) details.append(element("h3", "Calls from the callee"));
  for (const call of next.items) {
    details.append(button(call.expression ?? label(call.target), () => showStory(call.id, -1, true), "detail-btn"));
  }
  if (next.next_cursor) details.append(element("p", "More calls are available in the callee’s connections."));
}

function bindStory() {
  get("story").addEventListener("click", () => {
    showStory(state.hops[state.storyIndex]?.id, state.storyIndex).catch(showError);
  });
}
