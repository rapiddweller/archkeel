"use strict";
// AD-10: component flow view. No external library, no CDN, no Math.random/Date/timers -
// every run over the same embedded data produces the same layout.
(function () {
  const root = document.getElementById("flow");
  const dataNode = document.getElementById("flow-data");
  if (!root || !dataNode) return;
  const DATA = JSON.parse(dataNode.textContent);
  const CARD = { w: 200, h: 92 };
  const GAP = 34;
  const ROW_GAP = 150;
  const PER_ROW = 6;
  const ROW_STEP = CARD.h + ROW_GAP;
  const LANE_GAP = 11;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // The one place an EdgeState maps to a human label. Edge and chip elements already take their
  // color and dash pattern from the CSS class `edge ${state}` / `chip ${state}` (see
  // archkeel-report.css), so the legend swatches below reuse those same classes instead of a
  // second, hand-written color/dash list. A future third state (AD-15) is one new entry here.
  const EDGE_STATES = [
    { id: "conforms", label: "Conforms to the contract" },
    { id: "violation", label: "Violation" },
  ];

  const svg = root.querySelector(".flow-graph");
  const viewport = root.querySelector(".flow-viewport");
  const edgeLayer = viewport.querySelector(".flow-edges");
  const chipLayer = viewport.querySelector(".flow-chips");
  const nodeLayer = viewport.querySelector(".flow-nodes");
  const emptyLayer = viewport.querySelector(".flow-empty");
  const inspector = root.querySelector(".flow-inspector");
  const legend = root.querySelector(".flow-legend");
  const thresholdInput = root.querySelector(".flow-threshold");
  const thresholdValue = root.querySelector(".flow-threshold-value");
  const fitButton = root.querySelector(".flow-fit");

  // ponytail: pointer capture is best-effort. A browser can refuse it (no active pointer, an
  // already-captured element); the drag/pan state machine below tolerates that silently.
  function capturePointer(target, event) {
    try {
      target.setPointerCapture(event.pointerId);
    } catch {
      /* best-effort; pointermove/pointerup still drive the drag or pan via bubbling */
    }
  }

  const esc = (value) =>
    String(value).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function el(tag, attrs, ...children) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    children.forEach((child) => node.appendChild(child));
    return node;
  }

  function groupBy(items, keyOf) {
    const groups = new Map();
    items.forEach((item) => {
      const key = keyOf(item);
      const bucket = groups.get(key);
      if (bucket) bucket.push(item);
      else groups.set(key, [item]);
    });
    return groups;
  }

  const componentByLabel = new Map(DATA.components.map((c) => [c.label, c]));
  const edgeKey = (e) => `${e.source}>${e.target}`;
  let positions = {};
  let selected = null;
  let transform = { x: 0, y: 0, k: 1 };

  function computeRanks() {
    const rank = new Map(DATA.components.map((c) => [c.label, 0]));
    // Violated edges are excluded: a declared-rule violation is exactly the evidence that the
    // pair should not be read as forward architectural flow, so it must not drive layer depth.
    const forward = DATA.edges.filter((e) => e.state !== "violation");
    for (let pass = 0; pass < DATA.components.length; pass += 1) {
      forward.forEach((e) => {
        rank.set(e.target, Math.max(rank.get(e.target), rank.get(e.source) + 1));
      });
    }
    return rank;
  }

  function layout() {
    const rank = computeRanks();
    const byRank = groupBy(DATA.components, (c) => rank.get(c.label));
    const ranks = [...byRank.keys()].sort((a, b) => a - b);
    const next = {};
    let row = 0;
    ranks.forEach((r) => {
      const members = byRank.get(r).map((c) => c.label).sort();
      for (let start = 0; start < members.length; start += PER_ROW) {
        const chunk = members.slice(start, start + PER_ROW);
        const total = chunk.length * CARD.w + (chunk.length - 1) * GAP;
        chunk.forEach((label, index) => {
          if (!positions[label]) {
            next[label] = { x: index * (CARD.w + GAP) - total / 2, y: row * ROW_STEP };
          }
        });
        row += 1;
      }
    });
    positions = { ...next, ...positions };
    return row;
  }

  function portX(node, index, count) {
    const inset = 24;
    const span = CARD.w - 2 * inset;
    const at = count === 1 ? span / 2 : (span * index) / (count - 1);
    return positions[node].x + inset + at;
  }

  // Lane bucketing (AD-10 revision): every edge between the same two rows used to bend at the
  // exact same horizontal line, so parallel crossings piled into one unreadable band. Each edge
  // now gets its own bend line, offset by its position within that row-pair's lane.
  function laneKey(edge) {
    return `${positions[edge.source].y}:${positions[edge.target].y}`;
  }

  function laneOffsetFor(edge, lanes) {
    const lane = lanes.get(laneKey(edge));
    const index = lane.indexOf(edge);
    return (index - (lane.length - 1) / 2) * LANE_GAP;
  }

  function routeFor(edge, outIndex, inIndex, outCount, inCount, laneOffset) {
    const sx = portX(edge.source, outIndex, outCount);
    const tx = portX(edge.target, inIndex, inCount);
    const sPos = positions[edge.source];
    const tPos = positions[edge.target];
    const sameRow = sPos.y === tPos.y;
    const upward = tPos.y < sPos.y;
    if (sameRow) {
      const sy = sPos.y + CARD.h;
      const drop = sy + 56 + Math.abs(laneOffset) + (laneOffset < 0 ? LANE_GAP / 2 : 0);
      const dir = Math.sign(tx - sx) || 1;
      return {
        d: `M${sx},${sy} V${drop - 8} Q${sx},${drop} ${sx + dir * 8},${drop} H${tx - dir * 8} Q${tx},${drop} ${tx},${drop - 8} V${sy + 6}`,
        mid: [(sx + tx) / 2, drop],
      };
    }
    const sy = upward ? sPos.y : sPos.y + CARD.h;
    const ty = upward ? tPos.y + CARD.h : tPos.y;
    const my = (sy + ty) / 2 + laneOffset;
    const dir = Math.sign(tx - sx);
    const vdir = Math.sign(ty - sy) || 1;
    const r = Math.min(10, Math.abs(tx - sx) / 2);
    const end = ty - vdir * 6;
    const d =
      dir === 0
        ? `M${sx},${sy} V${end}`
        : `M${sx},${sy} V${my - vdir * r} Q${sx},${my} ${sx + dir * r},${my} H${tx - dir * r} Q${tx},${my} ${tx},${my + vdir * r} V${end}`;
    return { d, mid: [(sx + tx) / 2, my] };
  }

  function weight(edge) {
    return edge.import_sites;
  }

  function visibleEdges() {
    const threshold = Number(thresholdInput.value || 0);
    return DATA.edges.filter((e) => e.state === "violation" || weight(e) >= threshold);
  }

  function related(edge) {
    if (!selected) return true;
    if (selected.type === "node") return edge.source === selected.label || edge.target === selected.label;
    return edgeKey(edge) === selected.key;
  }

  function relatedToSelection(label) {
    if (!selected) return true;
    if (selected.type === "node") {
      return label === selected.label || DATA.edges.some((e) => related(e) && (e.source === label || e.target === label));
    }
    const [source, target] = selected.key.split(">");
    return label === source || label === target;
  }

  function render() {
    // render() replaces every card and edge, which would otherwise silently drop keyboard focus.
    const focused = capturedFocus();
    emptyLayer.textContent = "";
    if (!DATA.components.length) {
      edgeLayer.textContent = "";
      nodeLayer.textContent = "";
      chipLayer.textContent = "";
      const text = el("text", { x: "0", y: "0", fill: "var(--ck-muted)" });
      text.textContent = "This observation declares no components.";
      emptyLayer.appendChild(text);
      renderInspector([]);
      return;
    }
    const rows = layout();
    // The panel used to be a fixed height that shrank large graphs to a third of its area (and
    // their text with it). Sizing it to the laid-out content keeps fit()'s scale close to 1.
    svg.style.height = `${Math.max(420, Math.min(860, rows * ROW_STEP + 170))}px`;
    const max = DATA.edges.reduce((acc, e) => Math.max(acc, weight(e)), 1);
    thresholdInput.max = String(max);
    if (Number(thresholdInput.value) > max) thresholdInput.value = String(max);
    thresholdValue.textContent = `≥ ${thresholdInput.value} import sites`;
    const visible = visibleEdges();
    const outs = groupBy(visible, (e) => e.source);
    const ins = groupBy(visible, (e) => e.target);
    const byX = (key) => (a, b) => positions[a[key]].x - positions[b[key]].x;
    const lanes = groupBy(visible, laneKey);
    lanes.forEach((bucket) =>
      bucket.sort(
        (a, b) => positions[a.source].x - positions[b.source].x || positions[a.target].x - positions[b.target].x,
      ),
    );
    const routed = visible.map((edge) => {
      const outList = [...outs.get(edge.source)].sort(byX("target"));
      const inList = [...ins.get(edge.target)].sort(byX("source"));
      return {
        edge,
        ...routeFor(
          edge,
          outList.indexOf(edge),
          inList.indexOf(edge),
          outList.length,
          inList.length,
          laneOffsetFor(edge, lanes),
        ),
      };
    });

    edgeLayer.textContent = "";
    routed.forEach((r) => {
      const line = el("path", {
        class: "line",
        d: r.d,
        "stroke-width": (1.4 + 4.5 * Math.sqrt(weight(r.edge) / max)).toFixed(2),
      });
      const title = el("title");
      title.textContent = `${r.edge.source} → ${r.edge.target}`;
      const select = () => {
        selected = { type: "edge", key: edgeKey(r.edge) };
        render();
      };
      const hit = el(
        "path",
        {
          class: "hit",
          d: r.d,
          tabindex: "0",
          role: "button",
          "aria-label": `${r.edge.source} to ${r.edge.target}, ${weight(r.edge)} import sites`,
          "data-key": edgeKey(r.edge),
        },
        title,
      );
      hit.addEventListener("click", (event) => {
        event.stopPropagation();
        select();
      });
      hit.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
      // The state name is the CSS class directly, so a future third state (AD-15) is one new
      // rule in flow.js's stylesheet hook, not a branch here.
      const group = el("g", { class: `edge ${r.edge.state}${related(r.edge) ? "" : " dim"}` }, line, hit);
      edgeLayer.appendChild(group);
      r.node = line;
    });

    chipLayer.textContent = "";
    const cardBoxes = DATA.components.map((c) => ({
      x: positions[c.label].x - 4,
      y: positions[c.label].y - 4,
      w: CARD.w + 8,
      h: CARD.h + 8,
    }));
    const overlaps = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
    const placed = [];
    const fractions = [0.5, 0.35, 0.65, 0.2, 0.8, 0.12, 0.88];
    // Violated edges' rule-id chips are placed first and always kept. A conforming edge's plain
    // weight badge is dropped instead, once every candidate spot on its own line collides, so two
    // labels never overlap.
    const byPriority = [...routed].sort((a, b) => (b.edge.state === "violation" ? 1 : 0) - (a.edge.state === "violation" ? 1 : 0));
    byPriority.forEach((r) => {
      const extra = r.edge.rule_ids.length > 1 ? ` +${r.edge.rule_ids.length - 1}` : "";
      const label = r.edge.rule_ids.length ? `${r.edge.rule_ids[0]}${extra}` : String(weight(r.edge));
      const text = el("text", { "text-anchor": "middle", "dominant-baseline": "central" });
      text.textContent = label;
      const rect = el("rect", { rx: "3", height: "18" });
      const group = el("g", { class: `chip ${r.edge.state}${related(r.edge) ? "" : " dim"}` }, rect, text);
      chipLayer.appendChild(group);
      const width = Math.max(24, text.getComputedTextLength() + 12);
      rect.setAttribute("x", String(-width / 2));
      rect.setAttribute("y", "-9");
      rect.setAttribute("width", String(width));
      const length = r.node.getTotalLength();
      let best = null;
      for (const fraction of fractions) {
        const point = r.node.getPointAtLength(length * fraction);
        const box = { x: point.x - width / 2 - 3, y: point.y - 12, w: width + 6, h: 24 };
        if (![...cardBoxes, ...placed].some((other) => overlaps(box, other))) {
          best = { point, box };
          break;
        }
      }
      if (!best && r.edge.state !== "violation") {
        chipLayer.removeChild(group);
        return;
      }
      if (!best) {
        // A rule id must stay visible even in a tight spot: fall back to the path midpoint
        // rather than disappearing (this only happens if every one of the seven spots collides).
        const point = r.node.getPointAtLength(length * 0.5);
        best = { point, box: { x: point.x - width / 2 - 3, y: point.y - 12, w: width + 6, h: 24 } };
      }
      placed.push(best.box);
      group.setAttribute("transform", `translate(${best.point.x},${best.point.y})`);
    });

    nodeLayer.textContent = "";
    DATA.components.forEach((component) => {
      const pos = positions[component.label];
      const isSelected = selected && selected.type === "node" && selected.label === component.label;
      const dim = selected && !isSelected && !relatedToSelection(component.label);
      const hasViolation = DATA.edges.some(
        (e) => e.state === "violation" && (e.source === component.label || e.target === component.label),
      );
      const card = el("rect", { class: "card", width: String(CARD.w), height: String(CARD.h), rx: "8" });
      const tick = el("rect", {
        class: `tick${hasViolation ? " violated" : ""}`,
        width: "3",
        height: String(CARD.h - 24),
        x: "0",
        y: "12",
      });
      const label = el("text", { class: "label", x: "16", y: "30" });
      label.textContent = component.label;
      const meta = el("text", { class: "meta", x: "16", y: "56" });
      meta.textContent = `${component.modules.length} module${component.modules.length === 1 ? "" : "s"} · ${
        component.public === null ? "no public" : `public ${component.public.length}`
      }`;
      const group = el(
        "g",
        {
          class: `node${isSelected ? " selected" : ""}${dim ? " dim" : ""}`,
          transform: `translate(${pos.x},${pos.y})`,
          tabindex: "0",
          role: "button",
          "aria-label": `${component.label}, ${component.modules.length} modules`,
          "data-label": component.label,
        },
        card,
        tick,
        label,
        meta,
      );
      const select = () => {
        selected = { type: "node", label: component.label };
        render();
      };
      group.addEventListener("click", (event) => {
        event.stopPropagation();
        select();
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
      // Drag state lives at IIFE scope (dragState), not in this closure: render() rebuilds every
      // node on each frame, so a per-node variable would reset to null on the very next move.
      group.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        capturePointer(svg, event);
        dragState = { label: component.label, x: event.clientX, y: event.clientY, start: { ...pos } };
      });
      nodeLayer.appendChild(group);
    });

    restoreFocus(focused);
    renderInspector(visible);
  }

})();
