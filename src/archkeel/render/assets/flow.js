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
  // second, hand-written color/dash list.
  const EDGE_STATES = [
    { id: "conforms", label: "Conforms to the contract" },
    { id: "violation", label: "Violation" },
    { id: "undecided", label: "Undecided" },
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
  const backButton = root.querySelector(".flow-back");

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

  // AD-24: inside a component nothing is decided, so every inner edge is drawn as observed.
  // AD-24a: a module opens the same way, one level deeper, in the same {components, edges}
  // shape, because layout, ranking, routing and the inspector all consume that shape.
  function level() {
    if (!opened) return { components: DATA.components, edges: DATA.edges };
    if (opened.module) return moduleLevel(opened.module);
    const component = componentByLabel.get(opened.component);
    // Name a module relative to the package its component owns, so the package __init__ and
    // its submodules read the same way: `store` and `repository`, not `shop.store` and
    // `store.repository`.
    const prefix = component.modules.reduce(
      (acc, name) => (acc === null ? name : acc.split(".").filter((part, index) => name.split(".")[index] === part).join(".")),
      null,
    );
    const short = (name) => {
      if (!prefix || name === prefix) return name.split(".").pop() || name;
      return name.startsWith(`${prefix}.`) ? name.slice(prefix.length + 1) : name;
    };
    const isPublic = (name) =>
      component.public !== null && component.public.some((entry) => entry.split(":")[0] === name);
    return {
      components: component.modules.map((module) => ({
        label: module,
        display: short(module),
        modules: [],
        openable: Boolean((DATA.modules || {})[module]),
        public: isPublic(module) ? [module] : null,
      })),
      // A rule scoped below the component decides an inner pair, and sibling_isolation
      // decides peers: the verdict comes from the observation, it is not assumed here.
      edges: (component.inner_edges || []).map((edge) => ({
        source: edge.source,
        target: edge.target,
        import_sites: edge.import_sites,
        rule_ids: edge.rule_ids || [],
        state: edge.state || "undecided",
        names: [],
      })),
    };
  }
  // The declared names a module publishes outward, kept for the inspector on level three.
  function moduleLevel(name) {
    const inside = (DATA.modules || {})[name] || { symbols: [], edges: [] };
    const exported = new Set(inside.exports || []);
    return {
      components: inside.symbols.map((symbol) => ({
        label: symbol.name,
        display: symbol.name,
        kind: symbol.kind,
        members: symbol.members || [],
        modules: [],
        openable: false,
        // A symbol another module imports is this module's interface outward.
        public: exported.has(symbol.name) ? [symbol.name] : null,
      })),
      // One edge per pair: a call and a reference between the same two symbols say the same
      // thing here, which is that one uses the other.
      edges: inside.edges.map((edge) => ({
        source: edge.source,
        target: edge.target,
        import_sites: 1,
        rule_ids: [],
        state: "undecided",
        names: [],
      })),
    };
  }
  // AD-24: the first tap traces a card, the second opens what is behind it. A card is openable
  // while a deeper level exists: components always, modules that hold symbols. One function for
  // mouse, touch and keyboard, so the three can never drift apart.
  function selectCard(label) {
    const card = level().components.find((c) => c.label === label);
    if (!card) return;
    const openable = opened ? card.openable : true;
    if (openable && selected && selected.type === "node" && selected.label === label) {
      enter(label);
      return;
    }
    selected = { type: "node", label };
    render();
  }

  const edgeKey = (e) => `${e.source}>${e.target}`;
  let positions = {};
  let opened = null;
  let selected = null;
  let transform = { x: 0, y: 0, k: 1 };

  function computeRanks() {
    const view = level();
    const rank = new Map(view.components.map((c) => [c.label, 0]));
    // Violated edges are excluded: a declared-rule violation is exactly the evidence that the
    // pair should not be read as forward architectural flow, so it must not drive layer depth.
    const forward = view.edges.filter((e) => e.state !== "violation");
    for (let pass = 0; pass < view.components.length; pass += 1) {
      forward.forEach((e) => {
        rank.set(e.target, Math.max(rank.get(e.target), rank.get(e.source) + 1));
      });
    }
    return rank;
  }

  function layout() {
    const rank = computeRanks();
    const byRank = groupBy(level().components, (c) => rank.get(c.label));
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
    return level().edges.filter((e) => e.state === "violation" || weight(e) >= threshold);
  }

  function related(edge) {
    if (!selected) return true;
    if (selected.type === "node") return edge.source === selected.label || edge.target === selected.label;
    return edgeKey(edge) === selected.key;
  }

  function relatedToSelection(label) {
    if (!selected) return true;
    if (selected.type === "node") {
      return label === selected.label || level().edges.some((e) => related(e) && (e.source === label || e.target === label));
    }
    const [source, target] = selected.key.split(">");
    return label === source || label === target;
  }

  function capturedFocus() {
    const node = document.activeElement.closest(".node");
    if (node) return { kind: "node", key: node.getAttribute("data-label") };
    if (document.activeElement.classList.contains("hit")) {
      return { kind: "edge", key: document.activeElement.getAttribute("data-key") };
    }
    return null;
  }

  function restoreFocus(focused) {
    if (!focused) return;
    const attr = focused.kind === "node" ? "data-label" : "data-key";
    const selector = `[${attr}="${CSS.escape(focused.key)}"]`;
    const layer = focused.kind === "node" ? nodeLayer : edgeLayer;
    const target = layer.querySelector(selector);
    if (target) target.focus();
  }

  function render() {
    // render() replaces every card and edge, which would otherwise silently drop keyboard focus.
    const focused = capturedFocus();
    emptyLayer.textContent = "";
    if (!level().components.length) {
      edgeLayer.textContent = "";
      nodeLayer.textContent = "";
      chipLayer.textContent = "";
      const text = el("text", { x: "0", y: "0", fill: "var(--ck-muted)" });
      text.textContent = opened
        ? `${opened.module || opened.component} holds nothing to show.`
        : "This observation declares no components.";
      emptyLayer.appendChild(text);
      renderInspector([]);
      return;
    }
    const rows = layout();
    // The panel used to be a fixed height that shrank large graphs to a third of its area (and
    // their text with it). Sizing it to the laid-out content keeps fit()'s scale close to 1.
    svg.style.height = `${Math.max(420, Math.min(860, rows * ROW_STEP + 170))}px`;
    const max = level().edges.reduce((acc, e) => Math.max(acc, weight(e)), 1);
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
      // The state name is the CSS class directly, so a new state is one new rule in
      // flow.js's stylesheet hook, not a branch here.
      // A second, thin path carries the flow pulse. The base line keeps its dash pattern,
      // which is what tells a violation from an undecided pair - animating that pattern
      // would destroy the distinction the legend promises.
      const pulse = el("path", { class: "pulse", d: r.d });
      const group = el(
        "g",
        { class: `edge ${r.edge.state}${related(r.edge) ? "" : " dim"}` },
        line,
        pulse,
        hit,
      );
      edgeLayer.appendChild(group);
      r.node = line;
    });

    chipLayer.textContent = "";
    const cardBoxes = level().components.map((c) => ({
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
    level().components.forEach((component) => {
      const pos = positions[component.label];
      const isSelected = selected && selected.type === "node" && selected.label === component.label;
      const dim = selected && !isSelected && !relatedToSelection(component.label);
      const hasViolation = level().edges.some(
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
      label.textContent = component.display || component.label;
      const meta = el("text", { class: "meta", x: "16", y: "56" });
      meta.textContent = opened
        ? opened.module
          ? `${component.kind}${component.members.length ? ` · ${component.members.length} method${component.members.length === 1 ? "" : "s"}` : ""}${component.public === null ? "" : " · used outside"}`
          : component.public === null
            ? "internal"
            : "public"
        : `${component.modules.length} module${component.modules.length === 1 ? "" : "s"} · ${
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
      // A card's own click never fires for a mouse: its pointerdown captures the pointer on the
      // svg, and the capture retargets the click there too. Mouse taps therefore arrive through
      // endPointer below, and every path funnels into selectCard so all three behave alike.
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          selectCard(component.label);
        }
      });
      // Drag state lives at IIFE scope (dragState), not in this closure: render() rebuilds every
      // node on each frame, so a per-node variable would reset to null on the very next move.
      group.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        capturePointer(svg, event);
        dragState = {
          label: component.label,
          x: event.clientX,
          y: event.clientY,
          start: { ...pos },
          moved: 0,
        };
      });
      nodeLayer.appendChild(group);
    });

    restoreFocus(focused);
    renderInspector(visible);
  }

  function statBlock() {
    const view = level();
    const sites = view.edges.reduce((acc, e) => acc + weight(e), 0);
    if (opened && opened.module) {
      const inside = (DATA.modules || {})[opened.module] || {};
      const methods = view.components.reduce((acc, c) => acc + (c.members || []).length, 0);
      return `<dl class="kv"><dt>Symbols</dt><dd>${view.components.length}</dd><dt>Methods</dt><dd>${methods}</dd><dt>Uses inside</dt><dd>${view.edges.length}</dd><dt>Used from outside</dt><dd>${(inside.exports || []).length}</dd><dt>Reaches outward</dt><dd>${(inside.imports || []).length}</dd></dl>`;
    }
    if (opened) {
      return `<dl class="kv"><dt>Modules</dt><dd>${view.components.length}</dd><dt>Imports inside</dt><dd>${view.edges.length}</dd><dt>Import sites</dt><dd>${sites}</dd></dl>`;
    }
    const modules = view.components.reduce((acc, c) => acc + c.modules.length, 0);
    const violations = new Set(view.edges.flatMap((e) => e.rule_ids)).size;
    return `<dl class="kv"><dt>Components</dt><dd>${view.components.length}</dd><dt>Modules</dt><dd>${modules}</dd><dt>Edges</dt><dd>${view.edges.length}</dd><dt>Import sites</dt><dd>${sites}</dd><dt>Rules broken</dt><dd>${violations}</dd></dl>`;
  }

  function topHeaviestEdges(limit) {
    return [...level().edges]
      .sort(
        (a, b) => weight(b) - weight(a) || a.source.localeCompare(b.source) || a.target.localeCompare(b.target),
      )
      .slice(0, limit);
  }

  function heaviestBlock() {
    const top = topHeaviestEdges(5);
    if (!top.length) return "";
    const max = weight(top[0]) || 1;
    const rows = top
      .map(
        (e) =>
          `<div class="row" data-key="${esc(edgeKey(e))}" tabindex="0" role="button" aria-label="Select ${esc(e.source)} to ${esc(e.target)}"><span class="name">${esc(e.source)} → ${esc(e.target)}</span><em>${weight(e)}</em><span class="track"><b style="width:${(100 * weight(e)) / max}%"></b></span></div>`,
      )
      .join("");
    return `<h3>Heaviest connections</h3><div class="bars">${rows}</div>`;
  }

  function overview() {
    if (opened && opened.module) {
      const inside = (DATA.modules || {})[opened.module] || {};
      const reaches = (inside.imports || []).slice(0, 12).map((name) => `<li><code>${esc(name)}</code></li>`).join("");
      return `<div class="kicker">Inside</div><h2>${esc(opened.module)}</h2><p>The functions and classes it declares and the calls and references between them; methods are listed on the card of the class that owns them. A card marked public is imported by another module (AD-24a). Press Escape or use Back to leave.</p>${statBlock()}${reaches ? `<h3>Reaches outward</h3><ul class="names">${reaches}</ul>` : ""}`;
    }
    if (opened) {
      return `<div class="kicker">Inside</div><h2>${esc(opened.component)}</h2><p>Its modules and the imports between them, observed and undecided: no rule applies inside a component (AD-24). Click a module again to open it. Press Escape or use Back to leave.</p>${statBlock()}${heaviestBlock()}`;
    }
    return `<div class="kicker">Overview</div><h2>Component flow</h2><p>Select a card to see its modules and declared public interface, click it again to open it, or select a connector to see the exact names one component uses from another.</p>${statBlock()}${heaviestBlock()}`;
  }

  function wireHeaviestRows() {
    inspector.querySelectorAll(".bars .row[data-key]").forEach((row) => {
      const select = () => {
        selected = { type: "edge", key: row.getAttribute("data-key") };
        render();
      };
      row.addEventListener("click", select);
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
    });
  }

  function showOverview() {
    inspector.innerHTML = overview();
    wireHeaviestRows();
  }

  function renderInspector(visible) {
    if (!selected) {
      showOverview();
      return;
    }
    if (selected.type === "node") {
      // Resolve the card inside the level on screen. componentByLabel holds the six declared
      // components and nothing else, so below the top level every selection failed to resolve
      // and was cleared on the very next render - which is why a second click never found one
      // to compare against, and no module could be opened (AD-24a).
      const component = level().components.find((c) => c.label === selected.label);
      if (!component) {
        selected = null;
        showOverview();
        return;
      }
      const uses = level().edges.filter((e) => e.source === component.label);
      const usedBy = level().edges.filter((e) => e.target === component.label);
      const relations = `<dt>Uses</dt><dd>${uses.map((e) => esc(e.target)).join(", ") || "—"}</dd>
        <dt>Used by</dt><dd>${usedBy.map((e) => esc(e.source)).join(", ") || "—"}</dd>`;
      if (opened && opened.module) {
        inspector.innerHTML = `<div class="kicker">Symbol</div><h2>${esc(component.label)}</h2>
          <dl class="kv"><dt>Kind</dt><dd>${esc(component.kind || "symbol")}</dd>
          <dt>Outside</dt><dd>${component.public === null ? "not imported elsewhere" : "imported by another module"}</dd>
          ${relations}</dl>
          ${(component.members || []).length ? `<h3>Methods</h3><ul class="plain">${component.members.map((m) => `<li><code>${esc(m)}</code></li>`).join("")}</ul>` : ""}`;
        return;
      }
      if (opened) {
        inspector.innerHTML = `<div class="kicker">Module</div><h2>${esc(component.label)}</h2>
          <dl class="kv">${relations}</dl>
          <p>${component.openable ? "Click it again to see the functions and classes inside it." : "Nothing declared inside it to open."}</p>`;
        return;
      }
      inspector.innerHTML = `<div class="kicker">Component</div><h2>${esc(component.label)}</h2>
        <dl class="kv"><dt>Modules</dt><dd>${component.modules.length}</dd>
        ${relations}</dl>
        <h3>Modules</h3><ul class="plain">${component.modules.map((m) => `<li><code>${esc(m)}</code></li>`).join("") || '<li class="empty">None observed.</li>'}</ul>
        <h3>Declared public interface</h3>${
          component.public === null
            ? '<p class="empty">No public interface declared; every module is reachable.</p>'
            : `<ul class="plain">${component.public.map((p) => `<li><code>${esc(p)}</code></li>`).join("") || '<li class="empty">Declared empty.</li>'}</ul>`
        }`;
      return;
    }
    // A heaviest-connections row (any edge, regardless of the threshold slider) can select an
    // edge the diagram is currently hiding, so fall back to the full edge list before giving up.
    const edge = visible.find((e) => edgeKey(e) === selected.key) || level().edges.find((e) => edgeKey(e) === selected.key);
    if (!edge) {
      selected = null;
      showOverview();
      return;
    }
    const grouped = groupBy(edge.names, (n) => n.name.split(":")[0]);
    const names = [...grouped.entries()]
      .map(
        ([module, items]) =>
          `<div class="group"><div><code>${esc(module)}</code></div><ul class="plain">${items
            .map(
              (n) =>
                `<li>${esc(n.name.split(":")[1] ?? n.name)} <small>${esc(n.kind)}</small>${
                  n.returns ? `<br><span class="sig">(${n.params.map(esc).join(", ")}) → ${esc(n.returns)}</span>` : ""
                }</li>`,
            )
            .join("")}</ul></div>`,
      )
      .join("");
    inspector.innerHTML = `<div class="kicker">Connection</div><h2>${esc(edge.source)} → ${esc(edge.target)}</h2>
      <dl class="kv"><dt>Import sites</dt><dd>${edge.import_sites}</dd><dt>Interface names</dt><dd>${edge.names.length}</dd></dl>
      ${
        edge.rule_ids.length
          ? `<h3>Broken rules</h3><ul class="plain">${edge.rule_ids.map((r) => `<li class="violation-card"><code>${esc(r)}</code></li>`).join("")}</ul>`
          : ""
      }
      ${edge.names.length ? `<h3>Names used across the boundary</h3>${names}` : ""}`;
  }

  function legendSwatch(state) {
    const swatch = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    swatch.setAttribute("class", "flow-legend-swatch");
    swatch.setAttribute("viewBox", "0 0 28 10");
    swatch.appendChild(el("g", { class: `edge ${state}` }, el("path", { class: "line", d: "M1,5 H27" })));
    return swatch;
  }

  function renderLegend() {
    if (!legend) return;
    legend.textContent = "";
    EDGE_STATES.forEach(({ id, label }) => {
      const item = document.createElement("span");
      item.className = "flow-legend-item";
      item.appendChild(legendSwatch(id));
      const text = document.createElement("span");
      text.textContent = label;
      item.appendChild(text);
      legend.appendChild(item);
    });
    const hint = document.createElement("span");
    hint.className = "flow-legend-hint";
    hint.textContent =
      "Arrow and pulse run from the importer to the imported. " +
      "Click a card or a line, click a card again to open it, drag cards, scroll to zoom.";
    legend.appendChild(hint);
  }

  function fit(animate) {
    const bounds = viewport.getBBox();
    if (!bounds.width || !bounds.height) return;
    const box = svg.getBoundingClientRect();
    const scale = Math.min(1.4, 0.9 * Math.min(box.width / bounds.width, box.height / bounds.height));
    transform = {
      k: scale,
      x: box.width / 2 - scale * (bounds.x + bounds.width / 2),
      y: box.height / 2 - scale * (bounds.y + bounds.height / 2),
    };
    applyTransform(animate && !reducedMotion);
  }

  function applyTransform(animate) {
    viewport.style.transition = animate ? "transform 250ms ease-out" : "none";
    viewport.setAttribute("transform", `translate(${transform.x},${transform.y}) scale(${transform.k})`);
  }

  // Both live at IIFE scope, and both are driven from svg's own listeners (not the node's or
  // viewport's): render() rebuilds every card and edge, which would drop a listener attached
  // to one of them mid-drag.
  let panState = null;
  let dragState = null;
  svg.addEventListener("pointerdown", (event) => {
    if (event.target !== svg) return;
    panState = { x: event.clientX, y: event.clientY, start: { ...transform } };
    capturePointer(svg, event);
  });
  svg.addEventListener("pointermove", (event) => {
    if (dragState) {
      const dx = (event.clientX - dragState.x) / transform.k;
      const dy = (event.clientY - dragState.y) / transform.k;
      dragState.moved = Math.max(dragState.moved, Math.abs(dx) + Math.abs(dy));
      positions[dragState.label] = { x: dragState.start.x + dx, y: dragState.start.y + dy };
      render();
      return;
    }
    if (!panState) return;
    transform = {
      ...panState.start,
      x: panState.start.x + (event.clientX - panState.x),
      y: panState.start.y + (event.clientY - panState.y),
    };
    applyTransform(false);
  });
  // A press that never moved is a tap, not a drag: three pixels of slack for an unsteady hand.
  const TAP_SLACK = 3;
  const endPointer = () => {
    const tapped = dragState && dragState.moved <= TAP_SLACK ? dragState.label : null;
    panState = null;
    dragState = null;
    if (tapped !== null) selectCard(tapped);
  };
  svg.addEventListener("pointerup", endPointer);
  svg.addEventListener("pointercancel", endPointer);
  svg.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const rect = svg.getBoundingClientRect();
      const cx = event.clientX - rect.left;
      const cy = event.clientY - rect.top;
      const factor = Math.exp(-event.deltaY * 0.001);
      const k = Math.min(2.4, Math.max(0.3, transform.k * factor));
      const ratio = k / transform.k;
      transform = {
        k,
        x: cx - ratio * (cx - transform.x),
        y: cy - ratio * (cy - transform.y),
      };
      applyTransform(false);
    },
    { passive: false },
  );
  svg.addEventListener("click", () => {
    if (!selected) return;
    selected = null;
    render();
  });

  function enter(label) {
    opened = opened ? { component: opened.component, module: label } : { component: label };
    selected = null;
    positions = {};
    backButton.hidden = false;
    backButton.textContent = opened.module
      ? `Back to ${opened.component}`
      : "Back to components";
    render();
    fit(false);
  }

  // One step back per press: a module returns to its component, a component to the overview.
  function leave() {
    if (!opened) return;
    opened = opened.module ? { component: opened.component } : null;
    selected = null;
    positions = {};
    backButton.hidden = opened === null;
    if (opened) backButton.textContent = "Back to components";
    render();
    fit(false);
  }

  backButton.addEventListener("click", leave);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") leave();
  });

  thresholdInput.addEventListener("input", render);
  // Fit used to move the camera only, which left a hand-dragged card where it was and offered
  // no way back to the computed arrangement.
  fitButton.addEventListener("click", () => {
    positions = {};
    render();
    fit(true);
  });

  renderLegend();
  render();
  fit(false);
  window.addEventListener("resize", () => fit(false));
})();
