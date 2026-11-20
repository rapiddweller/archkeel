"use strict";

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
    if (!index) return;
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
    const future = index > state.storyIndex + Number(!storyView.saved);
    const line = svgStoryNode("g", {
      class: (proofMarks[status] ? status : "unknown") + (current ? " now" : "") + (future ? " future" : ""),
    }, routes);
    svgStoryNode("path", { d }, line);
    svgStoryNode("circle", { cx: endX, cy: endY, r: 3.5 }, line);
    if (current && !reducedStoryMotion()) {
      const marker = svgStoryNode("circle", { r: 5, class: "story-moving-marker" }, line);
      svgStoryNode("animateMotion", { path: d, dur: "1.3s", fill: "freeze" }, marker);
    }
  });
}
