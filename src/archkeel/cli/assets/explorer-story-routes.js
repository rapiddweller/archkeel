import { cards, element } from "./studio-dom.js";
import { state } from "./studio-state.js";
import { proofMarks, reducedStoryMotion, storyStep, storySystemIcon, storyView } from "./explorer-story.js";
const transitions = { return: "return", process_request: "request", process_response: "response" };
const directions = { reads: "Reads · static", writes: "Writes · static", reads_writes: "Reads and writes · static" };
export function svgStoryNode(name, attributes, parent) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes))
        node.setAttribute(key, String(value));
    parent.append(node);
    return node;
}
export function paintStoryRoutes() {
    const routes = cards.querySelector(".story-routes");
    if (!routes)
        return;
    const timeline = routes.parentElement;
    if (!timeline)
        return;
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
        if (!index || index > state.storyIndex + Number(!storyView.saved))
            return;
        const step = storyStep(state.hops[index - Number(!storyView.saved)]);
        const status = step.status;
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
        const line = svgStoryNode("g", {
            class: (proofMarks[status] ? status : "unknown") + (current ? " now" : ""),
        }, routes);
        svgStoryNode("path", { d }, line);
        svgStoryNode("circle", { cx: endX, cy: endY, r: 3.5 }, line);
        const transition = step.transition && transitions[step.transition];
        if (transition) {
            svgStoryNode("text", { x: (x + endX) / 2, y: direction === 0 ? (previous.bottom + endY) / 2 : mid - 4,
                "text-anchor": "middle", class: "story-route-label" }, line).textContent = transition;
        }
        if (current && !reducedStoryMotion()) {
            const marker = svgStoryNode("circle", { r: 5, class: "story-moving-marker" }, line);
            svgStoryNode("animateMotion", { path: d, dur: "1.3s", fill: "freeze" }, marker);
        }
    });
    paintStoryExternal(true);
}
export function storyDirection(system) {
    if (!system.direction_evidence?.length)
        return "Direction unknown";
    return directions[system.direction ?? ""] ?? "Direction unknown";
}
export function paintStoryExternal(animate = false) {
    const stage = cards.querySelector(".story-stage");
    if (!stage)
        return;
    stage.querySelector(".story-external-routes")?.remove();
    const node = stage.querySelector(".story-node[aria-current='step']");
    const active = stage.querySelector(".story-external-card.active");
    if (!node || !active)
        return;
    const target = storyStep(state.hops[state.storyIndex]).external?.find((item) => item.system === active.dataset.system && item.status === "observed_call" && item.evidence?.length);
    if (!target)
        return;
    const frame = stage.getBoundingClientRect(), from = node.getBoundingClientRect(), to = active.getBoundingClientRect();
    const scale = frame.width / stage.offsetWidth || 1;
    const x1 = (from.right - frame.left) / scale, y1 = (from.top + from.height / 2 - frame.top) / scale;
    const x2 = (to.left - frame.left) / scale, y2 = (to.top + to.height / 2 - frame.top) / scale;
    const middle = (x1 + x2) / 2;
    const reverse = target.direction === "reads" && target.direction_evidence?.length;
    const d = reverse ? `M${x2} ${y2} H${middle} V${y1} H${x1}` : `M${x1} ${y1} H${middle} V${y2} H${x2}`;
    const svg = svgStoryNode("svg", { class: "story-external-routes", "aria-hidden": "true" }, stage);
    const verifiedDirection = storyDirection(target) !== "Direction unknown";
    const group = svgStoryNode("g", { class: target.binding === "unknown" || !verifiedDirection ? "unknown" : "observed" }, svg);
    svgStoryNode("path", { d }, group);
    svgStoryNode("circle", { cx: reverse ? x1 : x2, cy: reverse ? y1 : y2, r: 3.5 }, group);
    svgStoryNode("text", { x: middle + 4, y: (y1 + y2) / 2, class: "story-external-label" }, group)
        .textContent = storyDirection(target);
    if (animate && verifiedDirection && !reducedStoryMotion()) {
        const marker = svgStoryNode("circle", { r: 5, class: "story-moving-marker" }, group);
        svgStoryNode("animateMotion", { path: d, dur: "1.3s", fill: "freeze" }, marker);
        if (target.direction === "reads_writes") {
            const reverseMarker = svgStoryNode("circle", { r: 5, class: "story-moving-marker" }, group);
            const reversePath = `M${x2} ${y2} H${middle} V${y1} H${x1}`;
            svgStoryNode("animateMotion", { path: reversePath, dur: "1.3s", fill: "freeze" }, reverseMarker);
        }
    }
}
export function storyExternalRail(steps) {
    const systems = new Map();
    for (const step of steps)
        for (const system of step.external ?? []) {
            if (system.status === "observed_call" && system.evidence?.length)
                systems.set(system.system, system);
        }
    if (systems.size) {
        const rail = element("aside", "", "story-external-rail");
        rail.append(element("h3", "External systems · static evidence"));
        for (const system of systems.values()) {
            const active = (steps[state.storyIndex].external ?? []).find((item) => item.system === system.system && item.status === "observed_call" && item.evidence?.length);
            const evidence = active ?? system;
            const item = element("div", "", "story-external-card" + (active ? " active" : ""));
            item.dataset.system = system.system;
            item.append(element("strong", storySystemIcon(system.system) + " " + (system.label ?? system.system)));
            item.append(element("span", evidence.binding === "unknown" ? "Binding unknown" : "Static call"));
            if (active)
                item.append(element("span", storyDirection(evidence)));
            rail.append(item);
        }
        return rail;
    }
    return null;
}
