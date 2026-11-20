"use strict";

const storyView = { saved: null, context: null, timer: null };
const proofMarks = {
  proven: ["✓", "Proven"], claim: ["✎", "Claim"], declared: ["◇", "Declared"],
  unknown: ["?", "Unknown"], missing: ["×", "Missing"],
};
const reducedStoryMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

function endpoint(step, side) {
  const id = step[side];
  const item = known.get(id);
  return {
    name: step[side + "_name"] ?? item?.name ?? id ?? "Unresolved target",
    lane: label(step[side + "_owner"] ?? item?.parent ?? "Unresolved"),
  };
}

function storyStep(step) {
  if (storyView.saved) return { ...step, name: step.node };
  const target = endpoint(step, "target");
  return {
    ...step, ...target, title: step.expression,
    status: step.resolution === "resolved" ? "proven" : "unknown",
  };
}
function proof(step) {
  const [mark, name] = proofMarks[step.status] ?? proofMarks.unknown;
  return element("span", mark + " " + name, "story-proof " + (proofMarks[step.status] ? step.status : "unknown"));
}

function storyMode() {
  const request = ++state.request;
  state.items = [];
  state.edges = [];
  state.selected = null;
  setMapControls(false);
  get("map").setAttribute("aria-pressed", "false");
  get("story").setAttribute("aria-pressed", "true");
  get("previous").hidden = get("more").hidden = true;
  notice.textContent = "";
  drawArrows();
  return request;
}
function storyHeading(title) {
  get("view-title").textContent = title ?? "Story library";
  const nav = get("breadcrumbs");
  nav.replaceChildren(button("Stories", showStories));
  if (title) nav.append(element("span", "/", "muted"), element("strong", title));
}

function stopStoryPlayback() {
  clearInterval(storyView.timer);
  storyView.timer = null;
  get("story-play").textContent = "Play story";
}

function storyStatus() {
  const counts = new Map();
  for (const step of state.hops.map(storyStep)) {
    counts.set(step.status, (counts.get(step.status) ?? 0) + 1);
  }
  return [...counts].map(([status, count]) => count + " " + (proofMarks[status]?.[1] ?? "Unknown").toLowerCase()).join(" · ");
}

function svgStoryNode(name, attributes, parent) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  parent.append(node);
  return node;
}

function paintStoryRoutes() {
  const routes = cards.querySelector(".story-routes");
  if (!routes) return;
  const timeline = routes.parentNode;
  const bounds = timeline.getBoundingClientRect();
  const scale = bounds.width / timeline.offsetWidth || 1;
  const nodes = [...timeline.querySelectorAll(".story-node")];
  const positions = nodes.map((node) => {
    const rect = node.getBoundingClientRect();
    return {
      left: (rect.left - bounds.left) / scale, right: (rect.right - bounds.left) / scale,
      top: (rect.top - bounds.top) / scale, bottom: (rect.bottom - bounds.top) / scale,
    };
  });
  routes.replaceChildren();
  positions.forEach((next, index) => {
    if (!index || index > state.storyIndex + Number(!storyView.saved)) return;
    const status = storyStep(state.hops[index - Number(!storyView.saved)]).status;
    const previous = positions[index - 1];
    const x = (previous.left + previous.right) / 2;
    const mid = (next.top + next.bottom) / 2;
    const direction = Math.sign(next.left - previous.left);
    const endX = direction === 0 ? x : direction > 0 ? next.left : next.right;
    const endY = direction === 0 ? next.top : mid;
    const d = direction === 0
      ? `M${x} ${previous.bottom} V${endY}`
      : `M${x} ${previous.bottom} V${mid - 10} Q${x} ${mid} ${x + direction * 10} ${mid} H${endX}`;
    const current = index === state.storyIndex + Number(!storyView.saved);
    const line = svgStoryNode("g", { class: (proofMarks[status] ? status : "unknown") + (current ? " now" : "") }, routes);
    svgStoryNode("path", { d }, line);
    svgStoryNode("circle", { cx: endX, cy: endY, r: 3.5 }, line);
  });
}

function paintStory() {
  const steps = state.hops.map(storyStep);
  const entries = storyView.saved ? steps : [endpoint(state.hops[0], "source"), ...steps];
  const lanes = [...new Set(entries.map((step) => step.lane ?? "Owner unknown"))];
  const board = element("section", "", "story-board");
  board.setAttribute("aria-label", "Story lanes");
  board.style.setProperty("--story-lanes", lanes.length);
  const heading = element("div", "", "story-lane-headings");
  const timeline = element("div", "", "story-timeline");
  const activeLane = steps[state.storyIndex].lane ?? "Owner unknown";
  for (const [index, lane] of lanes.entries()) {
    const laneName = element("strong", lane, lane === activeLane ? "active" : "");
    heading.append(laneName);
    const rail = element("div", "", lane === activeLane ? "story-rail active" : "story-rail");
    rail.style.gridColumn = String(index + 1);
    timeline.append(rail);
  }
  board.append(heading, timeline);
  svgStoryNode("svg", { class: "story-routes", "aria-hidden": "true" }, timeline);

  let currentChapter;
  const chapters = new Map((storyView.saved?.chapters ?? []).map(({id, title}) => [id, title]));
  let row = 1;
  for (const [position, step] of entries.entries()) {
    const index = position - Number(!storyView.saved);
    if (step.chapter && step.chapter !== currentChapter) {
      currentChapter = step.chapter;
      const chapter = element("h3", chapters.get(currentChapter) ?? currentChapter, "story-chapter");
      chapter.style.gridRow = String(row++);
      chapter.style.visibility = index > state.storyIndex ? "hidden" : "";
      timeline.append(chapter);
    }
    const name = step.title ?? step.name ?? step.expression;
    const node = index < 0 ? element("div", "", "story-node story-origin")
      : button("", () => goToStoryStep(index), "story-node");
    node.style.gridColumn = String(lanes.indexOf(step.lane ?? "Owner unknown") + 1);
    node.style.gridRow = String(row++);
    node.append(element("strong", name));
    if (index < 0) node.append(element("span", "Caller", "meta"));
    else {
      node.append(proof(step));
      if (index === state.storyIndex) node.setAttribute("aria-current", "step");
      node.style.visibility = index > state.storyIndex ? "hidden" : "";
    }
    timeline.append(node);
  }
  for (const rail of timeline.querySelectorAll(".story-rail")) rail.style.gridRow = "1 / " + row;
  const top = viewport.scrollTop;
  const left = viewport.scrollLeft;
  cards.replaceChildren(board);
  viewport.scrollTo(left, top);
  paintStoryRoutes();
  if (reducedStoryMotion()) return;
  const active = timeline.querySelector("[aria-current='step']").getBoundingClientRect();
  const frame = viewport.getBoundingClientRect();
  viewport.scrollTo({
    top: top + active.top - frame.top - (frame.height - active.height) / 2,
    left: left + active.left - frame.left - (frame.width - active.width) / 2,
    behavior: "smooth",
  });
}
function showStoryControls() {
  const count = state.hops.length;
  get("story-controls").hidden = false;
  get("story-back").disabled = state.storyIndex === 0;
  get("story-next").disabled = state.storyIndex + 1 >= count;
  get("story-play").disabled = count < 2;
  get("story-position").textContent = `Step ${state.storyIndex + 1} / ${count}`;
  const progress = get("story-progress");
  const restoreFocus = progress.contains(document.activeElement);
  progress.replaceChildren();
  state.hops.forEach((item, index) => {
    const step = storyStep(item);
    const mark = button("", () => goToStoryStep(index));
    mark.setAttribute("aria-label", "Step " + (index + 1) + " · " + (step.title ?? step.name ?? step.expression));
    mark.title = mark.getAttribute("aria-label");
    if (index === state.storyIndex) mark.setAttribute("aria-current", "step");
    else if (index < state.storyIndex) mark.className = proofMarks[step.status] ? step.status : "unknown";
    progress.append(mark);
  });
  if (restoreFocus) progress.querySelector("[aria-current='step']").focus({ preventScroll: true });
}

function storyBox(title, content, className = "") {
  const box = element("section", "", "story-box " + className);
  box.append(element("h3", title), ...content);
  details.append(box);
}

function sourceSite(site) {
  const path = site.path ?? site.file;
  if (!path) return element("p", "No indexed source location.", "meta");
  const text = site.line ? path + ":" + site.line : path;
  return site.reference ? button(text, () => showSource(site.reference), "detail-btn")
    : element("p", text, "meta");
}

function paintCheckedStep(step) {
  if (step.note) storyBox("Story · Author claim", [element("p", step.note)]);
  const evidence = [proof(step)];
  if (step.name) evidence.push(element("p", step.name, "story-symbol"));
  if (step.reason) evidence.push(element("p", step.reason));
  if (step.defined_at) evidence.push(sourceSite(step.defined_at));
  for (const site of step.evidence ?? []) evidence.push(sourceSite(site));
  storyBox("Evidence", evidence);
  if (step.external?.length) {
    const systems = step.external.map((item) => {
      const text = [item.system, item.touched && "Observed touchpoint", item.direction && item.direction + " · Claim"];
      return element("p", text.filter(Boolean).join(" · "));
    });
    storyBox("External systems", systems);
  }
  if (step.question) storyBox("Question for the architect · Claim", [element("p", step.question)], "question");
  details.append(storyChat(storyView.saved.id));
}

async function goToStoryStep(index) {
  if (index < 0 || index >= state.hops.length) return;
  const request = ++state.request;
  state.storyIndex = index;
  const step = storyStep(state.hops[index]);
  paintStory();
  showStoryControls();
  selectionHeading(step.title ?? step.name ?? step.expression, "Step " + (index + 1) + " / " + state.hops.length);
  if (storyView.saved) {
    paintCheckedStep(step);
    return;
  }
  const evidence = [proof(step)];
  if (step.reason) evidence.push(element("p", step.reason));
  evidence.push(button("Inspect call evidence", () => {
    stopStoryPlayback();
    return showEvidence(step);
  }, "detail-btn"));
  storyBox("Evidence", evidence);
  if (!step.target) return;
  const next = await api("relations", { element: step.target, direction: "out", kind: "call", limit: 24 });
  if (request !== state.request) return;
  if (next.items.length) details.append(element("h3", "Calls from the callee"));
  for (const call of next.items) {
    details.append(button(call.expression ?? label(call.target), () => showStory(call.id, -1, true), "detail-btn"));
  }
  if (next.next_cursor) details.append(element("p", "More calls are available in the callee’s connections."));
}

function openCheckedStory(story) {
  storyMode();
  stopStoryPlayback();
  storyView.saved = story;
  setStoryLink(story.id);
  get("native-report").hidden = Boolean(story.coverage?.observed_only);
  state.hops = story.steps;
  storyHeading(story.title);
  get("breadcrumbs").append(element("span", storyStatus(), "story-status"));
  viewport.scrollTo(0, 0);
  if (state.hops.length) return goToStoryStep(0);
  cards.replaceChildren(element("p", "This story has no steps."));
  details.replaceChildren();
  get("story-controls").hidden = true;
}

async function showStory(id, index = -1, follow = false) {
  const request = storyMode();
  stopStoryPlayback();
  if (storyView.saved) state.hops = [];
  storyView.saved = null;
  setStoryLink(null);
  storyHeading("Call sequence");
  const result = await api("story", { id });
  if (request !== state.request) return;
  const [step] = result.items;
  if (!step) {
    cards.replaceChildren(element("p", result.reason ?? "No call evidence for this step.", "unknown"));
    details.replaceChildren();
    get("story-controls").hidden = true;
    return;
  }
  if (follow) {
    state.hops = [...state.hops.slice(0, state.storyIndex + 1), step];
    index = state.hops.length - 1;
  } else if (index < 0 || !state.hops.length) {
    state.hops = [step];
    index = 0;
    viewport.scrollTo(0, 0);
  }
  return goToStoryStep(index);
}

function storyChat(story, selection = storyView.context) {
  const panel = element("details", "", "story-chat");
  panel.append(element("summary", story ? "Revise story with chat" : selection ? "Explain flow with Codex" : "Draft a story with chat"));
  panel.addEventListener("toggle", () => { if (panel.open) stopStoryPlayback(); });
  panel.append(element("p", "Sends your question, relevant symbols and calls, and the story template "
    + "if present to the Codex account signed in on this computer."
    + (story ? " It also sends this checked story and saves the revision as a new story." : "")));
  const form = element("form", "");
  const label = element("label", story ? "What should change?" : "What story should Studio draft?");
  const prompt = element("textarea", "");
  prompt.required = true;
  prompt.maxLength = 2000;
  prompt.rows = 3;
  label.append(prompt);
  const send = element("button", "Send to Codex");
  const status = element("p", "");
  status.setAttribute("role", "status");
  form.append(label, send, status);
  panel.append(form);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const text = prompt.value.trim();
    if (!text) return;
    const request = state.request;
    send.disabled = true;
    status.textContent = "Drafting and checking story…";
    try {
      const body = { prompt: text };
      if (selection) body.element = selection;
      if (story) body.story = story;
      const reply = await fetch("/api/v1/story-chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const result = await reply.json();
      if (!reply.ok) throw new Error(result.error ?? "Story drafting failed.");
      if (state.request === request) await openCheckedStory(result);
    } catch (error) {
      status.textContent = error.message;
    } finally {
      send.disabled = false;
    }
  });
  return panel;
}

async function showStories() {
  storyView.context = state.selected ?? storyView.context;
  const request = storyMode();
  stopStoryPlayback();
  setStoryLink(null);
  storyHeading();
  get("story-controls").hidden = true;
  viewport.scrollTo(0, 0);
  cards.replaceChildren(element("p", "Loading stories…"));
  selectionHeading("Story library", "Story");
  details.append(storyChat());
  const { items } = await api("stories");
  if (request !== state.request) return;
  const list = element("section", "", "story-library");
  if (!items.length) list.append(element("p", "No saved stories. Draft one with chat, or follow a call from Architecture."));
  for (const item of items) {
    list.append(button(item.title ?? item.id, () => loadStory(item.id), "detail-btn"));
  }
  cards.replaceChildren(list);
}

async function loadStory(id) {
  const request = storyMode();
  storyHeading("Loading story…");
  const story = await api("stories", { id });
  if (request === state.request) await openCheckedStory(story);
}
function reopenStory() {
  storyMode();
  storyHeading(storyView.saved?.title ?? "Call sequence");
  if (storyView.saved) get("breadcrumbs").append(element("span", storyStatus(), "story-status"));
  return goToStoryStep(state.storyIndex);
}
function toggleStoryPlayback() {
  if (storyView.timer) return stopStoryPlayback();
  if (state.hops.length < 2) return;
  if (state.storyIndex + 1 === state.hops.length) goToStoryStep(0).catch(showError);
  get("story-play").textContent = "Pause";
  storyView.timer = setInterval(() => {
    goToStoryStep(state.storyIndex + 1).catch(showError);
    if (state.storyIndex + 1 >= state.hops.length) stopStoryPlayback();
  }, 4400);
}

function bindStory() {
  get("story").addEventListener("click", () => showStories().catch(showError));
  get("story-back").addEventListener("click", () => goToStoryStep(state.storyIndex - 1).catch(showError));
  get("story-next").addEventListener("click", () => goToStoryStep(state.storyIndex + 1).catch(showError));
  get("story-play").addEventListener("click", toggleStoryPlayback);
  new ResizeObserver(paintStoryRoutes).observe(cards);
  document.addEventListener("keydown", (event) => {
    if (get("story-controls").hidden || event.target.closest("input, textarea, select, [contenteditable]")) return;
    if (event.key === " " && !event.target.closest("button, a, summary")) {
      event.preventDefault();
      toggleStoryPlayback();
    } else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
      event.preventDefault();
      goToStoryStep(state.storyIndex + (event.key === "ArrowRight" ? 1 : -1)).catch(showError);
    }
  });
}
