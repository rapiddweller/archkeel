import { api, draftStory } from "./studio-api.js";
import { breakPath, button, cards, details, element, get, notice, showError, viewport } from "./studio-dom.js";
import { state, known } from "./studio-state.js";
import { drawArrows, label, selectionHeading, showEvidence, showSource } from "./explorer.js";
import { setMapControls, setStoryLink } from "./explorer-map.js";
import { showStories, showStory } from "./explorer-story-loading.js";
import { paintStoryExternal, paintStoryRoutes, storyDirection, storyExternalRail, svgStoryNode } from "./explorer-story-routes.js";
export const storyView = { saved: null, context: null, timer: null };
export const proofMarks = {
    proven: ["✓", "Proven"], claim: ["✎", "Claim"], declared: ["◇", "Declared"],
    unknown: ["?", "Unknown"], missing: ["×", "Missing"],
};
export const reducedStoryMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
function endpoint(step, side) {
    if (!("kind" in step))
        return { name: "Unresolved target", lane: "Unresolved" };
    const id = step[side];
    const item = id ? known.get(id) : undefined;
    return {
        name: step[`${side}_name`] ?? item?.name ?? id ?? "Unresolved target",
        lane: label(step[`${side}_owner`] ?? item?.parent ?? "Unresolved"),
    };
}
export function storySystemIcon(system) {
    if (["relational_database", "mongodb", "redis", "postgresql", "sqlite"].includes(system))
        return "⛁";
    if (["kafka", "rabbitmq"].includes(system))
        return "⇄";
    return "◇";
}
export function storyStep(step) {
    if ("node" in step)
        return { ...step, name: step.node };
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
export function storyMode() {
    ++state.request;
    state.items = [];
    state.edges = [];
    state.selected = null;
    setMapControls(false);
    get("map").setAttribute("aria-pressed", "false");
    get("story").setAttribute("aria-pressed", "true");
    get("previous").hidden = get("more").hidden = true;
    notice.textContent = "";
    drawArrows();
}
export function storyHeading(title) {
    get("view-title").textContent = title ?? "Story library";
    const nav = get("breadcrumbs");
    nav.replaceChildren(button("Stories", showStories));
    if (title)
        nav.append(element("span", "/", "muted"), element("strong", title));
}
export function stopStoryPlayback() {
    if (storyView.timer !== null)
        clearInterval(storyView.timer);
    storyView.timer = null;
    get("story-play").textContent = "Play story";
}
function storyStatus() {
    const counts = new Map();
    for (const step of state.hops.slice(0, state.storyIndex + 1).map(storyStep)) {
        counts.set(step.status, (counts.get(step.status) ?? 0) + 1);
    }
    return [...counts].map(([status, count]) => count + " " + (proofMarks[status]?.[1] ?? "Unknown").toLowerCase()).join(" · ");
}
function paintStory() {
    const steps = state.hops.map(storyStep);
    const entries = storyView.saved ? steps
        : [{ ...endpoint(state.hops[0], "source"), status: "unknown" }, ...steps];
    const lanes = [...new Set(entries.map((step) => step.lane ?? "Owner unknown"))];
    const board = element("section", "", "story-board");
    const stage = element("div", "", "story-stage");
    const flow = element("div", "", "story-flow");
    board.setAttribute("aria-label", "Story lanes");
    board.style.setProperty("--story-lanes", String(lanes.length));
    const heading = element("div", "", "story-lane-headings");
    const timeline = element("div", "", "story-timeline");
    const activeLane = steps[state.storyIndex].lane ?? "Owner unknown";
    for (const [index, lane] of lanes.entries()) {
        const laneName = breakPath(element("strong", "", lane === activeLane ? "active" : ""), lane);
        heading.append(laneName);
        const rail = element("div", "", lane === activeLane ? "story-rail active" : "story-rail");
        rail.style.gridColumn = String(index + 1);
        timeline.append(rail);
    }
    const scrollHint = lanes.length > 1
        ? element("p", "Scroll sideways to see all modules.", "story-scroll-hint") : null;
    if (scrollHint)
        flow.append(scrollHint);
    flow.append(heading, timeline);
    stage.append(flow);
    const externalRail = storyExternalRail(steps);
    if (externalRail)
        stage.append(externalRail);
    board.append(stage);
    svgStoryNode("svg", { class: "story-routes", "aria-hidden": "true" }, timeline);
    let currentChapter;
    const chapters = new Map((storyView.saved?.chapters ?? []).map(({ id, title }) => [id, title]));
    let row = 1;
    for (const [position, step] of entries.entries()) {
        const index = position - Number(!storyView.saved);
        if (step.chapter && step.chapter !== currentChapter) {
            currentChapter = step.chapter;
            const chapter = element("h3", chapters.get(currentChapter) ?? currentChapter, "story-chapter");
            chapter.style.gridRow = String(row++);
            if (index > state.storyIndex)
                chapter.style.visibility = "hidden";
            timeline.append(chapter);
        }
        const name = step.function ?? step.name ?? step.expression ?? step.title ?? "";
        const node = index < 0 ? element("div", "", "story-node story-origin")
            : button("", () => { stopStoryPlayback(); goToStoryStep(index).catch(showError); }, "story-node");
        node.style.gridColumn = String(lanes.indexOf(step.lane ?? "Owner unknown") + 1);
        node.style.gridRow = String(row++);
        node.append(element("strong", name));
        if (index < 0)
            node.append(element("span", "Caller", "meta"));
        else {
            const site = step.defined_at;
            if (site?.path) {
                node.append(breakPath(element("span", "", "story-step-title"), site.path.split("/").at(-1) + (site.line ? ":" + site.line : "")));
            }
            if (step.note)
                node.append(element("span", step.note, "story-narration"));
            for (const system of step.external ?? []) {
                if (system.status !== "observed_call" || !system.evidence?.length)
                    continue;
                const label = (system.label ?? system.system) + (system.binding === "unknown" ? " · binding unknown" : "");
                const badge = element("span", storySystemIcon(system.system) + " " + label, "story-system");
                if (system.binding === "unknown")
                    badge.classList.add("unknown");
                badge.title = system.reason ?? "Static call and import; runtime target is not verified.";
                node.append(badge);
            }
            node.append(proof(step));
            if (index === state.storyIndex)
                node.setAttribute("aria-current", "step");
            if (index > state.storyIndex)
                node.style.visibility = "hidden";
        }
        timeline.append(node);
    }
    for (const rail of timeline.querySelectorAll(".story-rail"))
        rail.style.gridRow = "1 / " + row;
    const top = viewport.scrollTop;
    const left = viewport.scrollLeft;
    cards.replaceChildren(board);
    if (scrollHint)
        scrollHint.hidden = viewport.scrollWidth <= viewport.clientWidth;
    viewport.scrollTo(left, top);
    paintStoryRoutes();
    const active = timeline.querySelector("[aria-current='step']")?.getBoundingClientRect();
    if (!active)
        return;
    const frame = viewport.getBoundingClientRect();
    const panel = details.getBoundingClientRect();
    const overlaps = panel.left < frame.right && panel.right > frame.left && panel.top < frame.bottom;
    const visibleHeight = overlaps ? Math.max(0, panel.top - frame.top) : frame.height;
    const target = stage.querySelector(".story-external-card.active")?.getBoundingClientRect();
    const bothFit = target && Math.max(active.right, target.right) - Math.min(active.left, target.left) <= frame.width;
    const focusLeft = bothFit ? Math.min(active.left, target.left) : active.left;
    const focusWidth = bothFit ? Math.max(active.right, target.right) - focusLeft : active.width;
    viewport.scrollTo({
        top: top + active.top - frame.top - (visibleHeight - active.height) / 2,
        left: left + focusLeft - frame.left - (frame.width - focusWidth) / 2,
        behavior: reducedStoryMotion() ? "auto" : "smooth",
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
        const mark = button("", () => { stopStoryPlayback(); goToStoryStep(index).catch(showError); });
        mark.title = "Step " + (index + 1) + " · " + (step.title ?? step.name ?? step.expression);
        mark.setAttribute("aria-label", mark.title);
        if (index === state.storyIndex)
            mark.setAttribute("aria-current", "step");
        else if (index < state.storyIndex)
            mark.className = proofMarks[step.status] ? step.status : "unknown";
        progress.append(mark);
    });
    if (restoreFocus)
        progress.querySelector("[aria-current='step']")?.focus({ preventScroll: true });
}
function storyBox(title, content, className = "") {
    const box = element("section", "", "story-box " + className);
    box.append(element("h3", title), ...content);
    details.append(box);
}
function sourceSite(site) {
    const path = site.path ?? site.file;
    if (!path)
        return element("p", "No indexed source location.", "meta");
    const text = site.line ? path + ":" + site.line : path;
    const reference = site.reference;
    return breakPath(reference ? button("", () => showSource(reference), "detail-btn")
        : element("p", "", "meta"), text);
}
function paintCheckedStep(step, story) {
    if (step.note)
        storyBox("Story · Author claim", [element("p", step.note)]);
    const evidence = [proof(step)];
    if (step.name)
        evidence.push(breakPath(element("p", "", "story-symbol"), step.name));
    if (step.reason)
        evidence.push(element("p", step.reason));
    if (step.defined_at)
        evidence.push(sourceSite(step.defined_at));
    for (const site of step.evidence ?? [])
        evidence.push(sourceSite(site));
    storyBox("Evidence", evidence);
    if (step.external?.length) {
        const systems = step.external.flatMap((item) => {
            const observed = item.status === "observed_call" && item.evidence?.length;
            const label = (item.label ?? item.system) + (item.binding === "unknown" ? " · binding unknown" : "");
            const text = (observed ? storySystemIcon(item.system) + " " : "? ") + label
                + (observed ? " · Static call" : " · Claim");
            return [element("p", text), element("p", item.reason ?? "Runtime use is not verified.", "meta"),
                ...(observed ? item.evidence.map(sourceSite) : []),
                ...(observed && item.direction_evidence?.length ? [element("p", storyDirection(item), "meta"),
                    element("p", item.direction_reason ?? "Static evidence; runtime execution is not verified.", "meta"),
                    ...item.direction_evidence.map(sourceSite)] : [])];
        });
        storyBox("External systems", systems);
    }
    if (step.question)
        storyBox("Question for the architect · Claim", [element("p", step.question)], "question");
    details.append(storyChat(story.id));
}
export async function goToStoryStep(index) {
    if (index < 0 || index >= state.hops.length)
        return;
    const request = ++state.request;
    state.storyIndex = index;
    const hop = state.hops[index];
    const step = storyStep(hop);
    const status = get("breadcrumbs").querySelector(".story-status");
    if (status && storyView.saved)
        status.textContent = storyStatus();
    paintStory();
    showStoryControls();
    selectionHeading(step.title ?? step.function ?? step.name ?? step.expression ?? "", "Step " + (index + 1) + " / " + state.hops.length);
    if (storyView.saved) {
        paintCheckedStep(step, storyView.saved);
        return;
    }
    if (!("kind" in hop))
        return;
    const evidence = [proof(step)];
    if (step.reason)
        evidence.push(element("p", step.reason));
    evidence.push(button("Inspect call evidence", () => {
        stopStoryPlayback();
        return showEvidence(hop);
    }, "detail-btn"));
    storyBox("Evidence", evidence);
    if (!hop.target)
        return;
    const next = await api("relations", { element: hop.target, direction: "out", kind: "call", limit: 24 });
    if (request !== state.request)
        return;
    if (next.items.length)
        details.append(element("h3", "Calls from the callee"));
    for (const call of next.items) {
        details.append(button(call.expression ?? label(call.target ?? ""), () => showStory(call.id, -1, true), "detail-btn"));
    }
    if (next.next_cursor)
        details.append(element("p", "More calls are available in the callee’s connections."));
}
export function openCheckedStory(story) {
    storyMode();
    stopStoryPlayback();
    storyView.saved = story;
    setStoryLink(story.id);
    get("native-report").hidden = Boolean(story.coverage?.observed_only);
    state.hops = story.steps;
    storyHeading(story.title);
    get("breadcrumbs").append(element("span", storyStatus(), "story-status"));
    viewport.scrollTo(0, 0);
    if (state.hops.length)
        return goToStoryStep(0);
    cards.replaceChildren(element("p", "This story has no steps."));
    details.replaceChildren();
    get("story-controls").hidden = true;
}
export function storyChat(story, selection = storyView.context) {
    const panel = element("details", "", "story-chat");
    panel.append(element("summary", story ? "Revise story with chat" : selection ? "Explain flow with Codex" : "Draft a story with chat"));
    panel.addEventListener("toggle", () => { if (panel.open)
        stopStoryPlayback(); });
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
        if (!text)
            return;
        const request = state.request;
        send.disabled = true;
        status.textContent = "Drafting and checking story…";
        try {
            const body = { prompt: text };
            if (selection)
                body.element = selection;
            if (story)
                body.story = story;
            const result = await draftStory(body);
            if (state.request === request)
                await openCheckedStory(result);
        }
        catch (error) {
            status.textContent = error instanceof Error ? error.message : "Story drafting failed.";
        }
        finally {
            send.disabled = false;
        }
    });
    return panel;
}
export function reopenStory() {
    storyMode();
    storyHeading(storyView.saved?.title ?? "Call sequence");
    if (storyView.saved)
        get("breadcrumbs").append(element("span", storyStatus(), "story-status"));
    return goToStoryStep(state.storyIndex);
}
function toggleStoryPlayback() {
    if (storyView.timer)
        return stopStoryPlayback();
    if (state.hops.length < 2)
        return;
    if (state.storyIndex + 1 === state.hops.length)
        goToStoryStep(0).catch(showError);
    get("story-play").textContent = "Pause";
    storyView.timer = setInterval(() => {
        goToStoryStep(state.storyIndex + 1).catch(showError);
        if (state.storyIndex + 1 >= state.hops.length)
            stopStoryPlayback();
    }, 4400);
}
export function bindStory() {
    const tab = get("story");
    tab.addEventListener("click", () => showStories().catch(showError));
    tab.disabled = false;
    get("story-back").addEventListener("click", () => { stopStoryPlayback(); goToStoryStep(state.storyIndex - 1).catch(showError); });
    get("story-next").addEventListener("click", () => { stopStoryPlayback(); goToStoryStep(state.storyIndex + 1).catch(showError); });
    get("story-play").addEventListener("click", toggleStoryPlayback);
    new ResizeObserver(paintStoryRoutes).observe(cards);
    let externalScrollTimer;
    viewport.addEventListener("scroll", () => {
        clearTimeout(externalScrollTimer);
        externalScrollTimer = setTimeout(() => paintStoryExternal(true), 160);
    }, { passive: true });
    document.addEventListener("keydown", (event) => {
        if (!(event.target instanceof Element) || get("story-controls").hidden || event.target.closest("input, textarea, select, [contenteditable]"))
            return;
        if (event.key === " " && !event.target.closest("button, a, summary")) {
            event.preventDefault();
            toggleStoryPlayback();
        }
        else if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
            event.preventDefault();
            stopStoryPlayback();
            goToStoryStep(state.storyIndex + (event.key === "ArrowRight" ? 1 : -1)).catch(showError);
        }
    });
}
