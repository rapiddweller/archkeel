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
    { id: "undecided", label: "Undecided: a decision is owed" },
    { id: "observed", label: "Observed inside a component: no boundary rule applies" },
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
  const violationFocus = root.querySelector(".flow-violation-focus");
  const violationsOnly = root.querySelector(".flow-violations-only");
  const fitButton = root.querySelector(".flow-fit");
  const backButton = root.querySelector(".flow-back");
  const breadcrumb = root.querySelector(".flow-breadcrumb");

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

  function scopeRules(scope) {
    return scope?.rules || (scope?.rule_id ? [{
      rule_id: scope.rule_id, rationale: scope.rationale, decided_by: scope.decided_by,
    }] : []);
  }

  function scopeRuleList(scope) {
    const rules = scopeRules(scope);
    if (!rules.length) return "<p>No scope rule details recorded.</p>";
    const values = (label, items) => items?.length
      ? `<br>${label}: ${items.map((value) => `<code>${esc(value)}</code>`).join(", ")}`
      : "";
    const items = rules.map((rule) => {
      const rationale = rule.rationale ? ` — ${esc(rule.rationale)}` : "";
      const decider = rule.decided_by ? ` (${esc(rule.decided_by)})` : "";
      return `<li><code>${esc(rule.rule_id)}</code>${rationale}${decider}`
        + values("Allowed", rule.allowed_sources)
        + values("Exact", rule.exact_sources)
        + values("Provenance", rule.provenance)
        + values("Evidence", rule.evidence)
        + "</li>";
    });
    return `<ul class="plain">${items.join("")}</ul>`;
  }

  const rootCards = DATA.components.concat(DATA.libraries || [], DATA.unassigned ? [DATA.unassigned] : []);
  const componentByLabel = new Map(rootCards.map((c) => [c.label, c]));

  // AD-24: inner edges stay observed unless the declared inside rules decide their pair.
  // AD-24a: a module opens the same way, one level deeper, in the same {components, edges}
  // shape, because layout, ranking, routing and the inspector all consume that shape.
  function level() {
    if (!opened) return { components: rootCards, edges: DATA.edges };
    if (opened.module) return moduleLevel(opened.module);
    const component = componentByLabel.get(opened.component);
    // AD-34: a component whose contract describes its inside opens into that level first, and
    // its modules sit one step deeper, inside the sub-component that owns them.
    if (opened.inside) {
      const card = (component.inside.components || []).find((c) => c.label === opened.inside);
      return card ? cardLevel(card, opened.path || []) : { components: [], edges: [] };
    }
    if (component.inside) return insideLevel(component.inside);
    return cardLevel(component, opened.path || []);
  }

  function insideLevel(inside) {
    const cards = inside.components.map((card) => ({
      label: card.label,
      modules: card.modules,
      openable: card.modules.length > 0,
      public: card.public,
    }));
    // A module no sub-component owns keeps a card: one that vanished between two levels is
    // exactly what this tool exists to prevent (AD-34). Opening it opens the module itself.
    const orphans = (inside.unassigned || []).map((name) => ({
      label: name,
      display: name.split(".").pop() || name,
      modules: [],
      openable: Boolean((DATA.modules || {})[name]),
      opensModule: name,
      public: null,
    }));
    return {
      components: cards.concat(orphans),
      edges: inside.edges.map((edge) => ({ ...edge, names: [] })),
    };
  }

  function rootPackage(modules) {
    if (!modules.length) return "";
    if (modules.length === 1) return modules[0].split(".").slice(0, -1).join(".");
    const first = modules[0].split(".");
    let length = 0;
    while (length < first.length &&
      modules.slice(1).every((name) => name.split(".")[length] === first[length])) length += 1;
    return first.slice(0, length).join(".");
  }

  // Physical folders are navigation, not declared semantic components. Keep raw module
  // edges in the payload and aggregate only those crossing the folders currently on screen.
  function cardLevel(component, path) {
    const prefix = path.length ? path[path.length - 1] : rootPackage(component.modules);
    const groups = new Map();
    component.modules.forEach((name) => {
      if (prefix && name !== prefix && !name.startsWith(`${prefix}.`)) return;
      const rest = prefix ? name.slice(prefix.length).replace(/^\./, "") : name;
      const child = rest ? (prefix ? `${prefix}.${rest.split(".")[0]}` : rest.split(".")[0]) : prefix;
      if (!groups.has(child)) groups.set(child, []);
      groups.get(child).push(name);
    });
    const own = groups.get(prefix);
    if (own && groups.size > 1) {
      groups.delete(prefix);
      if ((DATA.modules || {})[prefix]) groups.set(`${prefix}:__init__`, own);
    }
    const cards = [...groups].map(([label, modules]) => {
      const folder = !label.endsWith(":__init__") && modules.some((name) => name !== label);
      const publicNames = (component.public || []).filter((entry) =>
        modules.some((module) => entry.split(":")[0] === module));
      const touching = (component.inner_edges || []).filter((edge) =>
        modules.includes(edge.source) || modules.includes(edge.target));
      return {
        label, display: label.endsWith(":__init__") ? "__init__" : label.split(".").pop(),
        modules, folder, openable: folder || Boolean((DATA.modules || {})[modules[0]]),
        opensModule: folder ? null : modules[0], public: publicNames.length ? publicNames : null,
        import_sites: touching.reduce((sum, edge) => sum + edge.import_sites, 0),
        internal_violation: touching.some((edge) => edge.state === "violation"),
      };
    }).sort((a, b) => a.label.localeCompare(b.label));
    const cardOf = new Map(cards.flatMap((card) => card.modules.map((name) => [name, card.label])));
    const edges = new Map();
    (component.inner_edges || []).forEach((edge) => {
      const source = cardOf.get(edge.source);
      const target = cardOf.get(edge.target);
      if (!source || !target || source === target) return;
      const key = `${source}>${target}`;
      const prior = edges.get(key);
      if (prior) {
        prior.import_sites += edge.import_sites;
        prior.rule_ids = [...new Set([...prior.rule_ids, ...(edge.rule_ids || [])])].sort();
        prior.sites = [...new Set([...prior.sites, ...(edge.sites || [])])].sort().slice(0, 3);
        if (edge.state === "violation") prior.state = "violation";
      } else {
        edges.set(key, { source, target, import_sites: edge.import_sites,
          rule_ids: [...(edge.rule_ids || [])], state: edge.state || "observed",
          sites: [...(edge.sites || [])], names: [] });
      }
    });
    return { components: cards, edges: [...edges.values()] };
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
        state: "observed",
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
    const openable = opened ? card.openable : !card.library;
    if (openable && selected && selected.type === "node" && selected.label === label) {
      enter(label);
      return;
    }
    selected = { type: "node", label };
    render();
  }

  const edgeKey = (e) => `${e.source}>${e.target}`;
  let positions = {};
  const linkedComponent = new URLSearchParams(window.location.hash.slice(1)).get("component");
  let opened = componentByLabel.has(linkedComponent) ? { component: linkedComponent, path: [] } : null;
  let selected = null;
  let transform = { x: 0, y: 0, k: 1 };

  function computeRanks() {
    const view = level();
    const rank = new Map(view.components.map((c) => [c.label, 0]));
    // Violated edges are excluded: a declared-rule violation is exactly the evidence that the
    // pair should not be read as forward architectural flow, so it must not drive layer depth.
    const forward = visibleEdges().filter((e) => e.state !== "violation");
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
        mid: [(sx + tx) / 2, drop], end: [tx, sy + 6],
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
    return { d, mid: [(sx + tx) / 2, my], end: [tx, end] };
  }

  function weight(edge) {
    return edge.import_sites;
  }

  // Dash lengths are multiples of the line's own width, never absolute pixels: a violation
  // reads as long strokes, an undecided pair as fine dots, at every weight. A conforming edge
  // stays solid, which is what makes the other two legible as exceptions.
  const DASH_RATIOS = { violation: [2.4, 1.8], undecided: [0.55, 1.5], observed: [1.6, 1.4] };
  function dashFor(state, width) {
    const ratio = DASH_RATIOS[state];
    if (!ratio) return {};
    return { "stroke-dasharray": ratio.map((part) => (part * width).toFixed(2)).join(" ") };
  }

  function visibleEdges() {
    const threshold = Number(thresholdInput.value || 0);
    return level().edges.filter(
      (e) => e.state === "violation" || (!violationsOnly.checked && weight(e) >= threshold),
    );
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
    updateNavigation();
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
    thresholdInput.disabled = violationsOnly.checked;
    const visible = visibleEdges();
    thresholdValue.textContent = `≥ ${thresholdInput.value} import sites · ${visible.length}/${level().edges.length} shown`;
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
      // One width for every edge. Weight is written on the line as a number instead, which a
      // reader can compare exactly rather than by eye, and which keeps every arrow head the
      // same size: a head scaled by its line reads as weight where it should read as
      // direction. The dash pattern still scales with this width, so each state keeps its
      // ratio and the meaning the legend promises.
      const width = 2;
      const line = el("path", {
        class: "line",
        d: r.d,
        "stroke-width": width.toFixed(2),
        ...dashFor(r.edge.state, width),
      });
      const title = el("title");
      const ruleText = (r.edge.rule_ids || []).map((id) => {
        const rule = (DATA.rules || {})[id] || {};
        return `${id}: ${rule.rationale || "rule rationale not recorded"}${rule.decided_by ? ` (${rule.decided_by})` : ""}`;
      }).join("; ");
      const through = r.edge.requirement?.through || [];
      const contractText = r.edge.library
        ? `External library use. ${scopeRules(r.edge.scope).map((rule) => `${rule.rule_id}: ${rule.rationale || "No rationale recorded"}${rule.decided_by ? ` (${rule.decided_by})` : ""}`).join("; ")}`
        : `${through.length ? `Interface narrowed through ${through.join(", ")}. ` : "Interface not narrowed. "}${r.edge.requirement?.rationale || ""}${r.edge.requirement?.decided_by ? ` (${r.edge.requirement.decided_by})` : ""}`;
      title.textContent = `${r.edge.source} uses ${r.edge.target}; ${weight(r.edge)} import sites; ${r.edge.state}. ${contractText} ${ruleText}${(r.edge.sites || []).length ? ` Example: ${r.edge.sites.join(", ")}` : ""}`;
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
      const assembly = !opened && r.edge.state === "conforms" && through.length
        ? el("g", { class: "uml-assembly" },
          el("circle", { cx: String(r.end[0]), cy: String(r.end[1]), r: "5" }),
          el("path", { d: `M${r.end[0] - 7},${r.end[1] - 6} Q${r.end[0] - 14},${r.end[1]} ${r.end[0] - 7},${r.end[1] + 6}` })) : null;
      const group = el(
        "g",
        { class: `edge ${r.edge.state}${r.edge.library ? " library-use" : ""}${related(r.edge) ? "" : " dim"}` },
        line,
        pulse,
        ...(assembly ? [assembly] : []),
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
    // Violated edges' rule-id chips are placed first, so they win the roomiest spots; a plain
    // weight badge takes what is left. Every label is kept either way - the number is the only
    // place weight is shown now, so dropping one would hide a measurement rather than tidy it.
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
      if (!best) {
        // Every label stays visible in a tight spot: fall back to the path midpoint rather
        // than disappearing. Weight is no longer drawn into the line, so a dropped number is
        // a number the reader cannot recover - and inside a component, where every edge is
        // observed and the spots are crowded, dropping was the common case, not the rare one.
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
      const hasViolation = component.internal_violation || level().edges.some(
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
      const label = el("text", { class: "label", x: "16", y: "37" });
      label.textContent = component.display || component.label;
      const stereotype = el("text", { class: "stereotype", x: "16", y: "17" });
      stereotype.textContent = component.navigation_only ? "«unassigned»" : component.library ? "«library»" : !opened ? "«component»" : opened.module ? "«code»" : component.folder ? "«package»" : "«module»";
      const meta = el("text", { class: "meta", x: "16", y: "68" });
      const modulesMeta = (card) =>
        `${card.modules.length} module${card.modules.length === 1 ? "" : "s"} · ${
          card.public === null ? "no public" : `public ${card.public.length}`
        }`;
      meta.textContent = opened
        ? opened.module
          ? `${component.kind}${component.members.length ? ` · ${component.members.length} method${component.members.length === 1 ? "" : "s"}` : ""}${component.public === null ? "" : " · used outside"}`
          : component.folder
            ? `${component.modules.length} modules · ${component.import_sites} import sites`
            : // A sub-component card holds modules, so it reads like a component, not like one.
            component.modules && component.modules.length > 1
            ? modulesMeta(component)
            : component.opensModule
              ? (component.public === null ? "internal part" : "provided part")
              : component.public === null
                ? "internal part"
                : "provided part"
        : component.navigation_only
          ? `${component.modules.length} modules · navigation only`
          : component.library ? `${component.import_sites} import sites` : modulesMeta(component);
      const umlIcon = !component.library && !component.navigation_only && (!opened || (opened.inside === undefined && component.modules && component.modules.length > 1))
        ? el("g", { class: "uml-icon" },
          el("rect", { x: "175", y: "12", width: "15", height: "17" }),
          el("rect", { x: "170", y: "16", width: "7", height: "4" }),
          el("rect", { x: "170", y: "23", width: "7", height: "4" })) : null;
      const provided = !opened && !component.navigation_only && component.public !== null && component.public.length
        ? el("g", { class: "uml-provided" },
          el("line", { x1: "200", y1: "45", x2: "213", y2: "45" }),
          el("circle", { cx: "219", cy: "45", r: "6" })) : null;
      const required = !opened && !component.navigation_only && component.requires && component.requires.length
        ? el("g", { class: "uml-required" },
          el("line", { x1: "0", y1: "45", x2: "-9", y2: "45" }),
          el("path", { d: "M-9,37 Q-18,45 -9,53" })) : null;
      const tooltip = el("title");
      tooltip.textContent = component.navigation_only
        ? `${component.label}: modules without a unique declared owner. Navigation only; no component boundary or contract verdict is implied. Select to inspect the module inventory.`
        : component.library
        ? `${component.display}: external library scope under ${scopeRules(component).map((rule) => rule.rule_id).join(", ")}.`
        : !opened
        ? `${component.label}: ${component.modules.length} modules; ${component.public === null ? "no interface boundary declared" : `${component.public.length} provided entries`}; ${(component.requires || []).length} required components. Select for details; select again to open.`
        : `${component.label}: ${component.folder ? "physical package, not a declared component" : "module"}; ${component.import_sites || 0} import sites touching it.`;
      const group = el(
        "g",
        {
          class: `node${isSelected ? " selected" : ""}${dim ? " dim" : ""}`,
          transform: `translate(${pos.x},${pos.y})`,
          tabindex: "0",
          role: "button",
          "aria-label": component.navigation_only
            ? `${component.modules.length} unassigned modules, navigation only`
            : component.library
            ? `${component.display}, external library, ${component.import_sites} import sites`
            : `${component.label}, ${component.modules.length} modules`,
          "data-label": component.label,
        },
        card,
        tick,
        stereotype,
        label,
        meta,
        ...(umlIcon ? [umlIcon] : []),
        ...(provided ? [provided] : []),
        ...(required ? [required] : []),
        tooltip,
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
          pointerType: event.pointerType,
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
      const owner = componentByLabel.get(opened.component);
      const card = opened.inside ? (owner.inside.components || []).find((item) => item.label === opened.inside) : owner;
      return `<dl class="kv"><dt>Modules</dt><dd>${card.modules.length}</dd><dt>Visible groups</dt><dd>${view.components.length}</dd><dt>Visible crossings</dt><dd>${view.edges.length}</dd><dt>Crossing import sites</dt><dd>${sites}</dd></dl>`;
    }
    const modules = view.components.reduce((acc, c) => acc + c.modules.length, 0);
    const libraries = view.components.filter((card) => card.library).length;
    const navigation = view.components.filter((card) => card.navigation_only).length;
    const violations = new Set(view.edges.flatMap((e) => e.rule_ids)).size;
    return `<dl class="kv"><dt>Components</dt><dd>${view.components.length - libraries - navigation}</dd><dt>Observed libraries</dt><dd>${libraries}</dd><dt>Unassigned module groups</dt><dd>${navigation}</dd><dt>Modules</dt><dd>${modules}</dd><dt>Edges</dt><dd>${view.edges.length}</dd><dt>Import sites</dt><dd>${sites}</dd><dt>Broken edge rules (this level)</dt><dd>${violations}</dd></dl>`;
  }

  function topHeaviestEdges(limit) {
    const edges = violationsOnly.checked ? visibleEdges() : level().edges;
    return [...edges]
      .sort(
        (a, b) => weight(b) - weight(a) || a.source.localeCompare(b.source) || a.target.localeCompare(b.target),
      )
      .slice(0, limit);
  }

  function heaviestBlock() {
    const top = topHeaviestEdges(5);
    if (!top.length) return emptyViolationBlock();
    const max = weight(top[0]) || 1;
    const rows = top
      .map(
        (e) =>
          `<div class="row" data-key="${esc(edgeKey(e))}" tabindex="0" role="button" aria-label="Select ${esc(e.source)} to ${esc(e.target)}"><span class="name">${esc(e.source)} → ${esc(e.target)}</span><em>${weight(e)}</em><span class="track"><b style="width:${(100 * weight(e)) / max}%"></b></span></div>`,
      )
      .join("");
    const heading = violationsOnly.checked ? "Violating connections" : "Heaviest connections";
    return `<h3>${heading}</h3><div class="bars">${rows}</div>`;
  }

  function emptyViolationBlock() {
    return violationsOnly.checked
      ? '<h3>Violating connections</h3><p class="empty">No violating edges at this level. Other violation kinds remain in the table above.</p>'
      : "";
  }

  function overview() {
    if (opened && opened.module) {
      const inside = (DATA.modules || {})[opened.module] || {};
      const reaches = (inside.imports || []).slice(0, 12).map((name) => `<li><code>${esc(name)}</code></li>`).join("");
      return `<div class="kicker">Inside</div><h2>${esc(opened.module)}</h2><p>The functions and classes it declares and the calls and references between them; methods are listed on the card of the class that owns them. A card marked public is imported by another module (AD-24a). Press Escape or use Back to leave.</p>${statBlock()}${reaches ? `<h3>Reaches outward</h3><ul class="names">${reaches}</ul>` : ""}${emptyViolationBlock()}`;
    }
    if (opened && !opened.inside && (componentByLabel.get(opened.component) || {}).inside) {
      return `<div class="kicker">Inside</div><h2>${esc(opened.component)}</h2><p>These are declared sub-components. A green connection is allowed; a red one breaks a rule. Select a card twice to open it.</p>${statBlock()}${heaviestBlock()}`;
    }
    if (opened) {
      const owner = componentByLabel.get(opened.component);
      const card = opened.inside ? (owner.inside.components || []).find((item) => item.label === opened.inside) : owner;
      const prefix = (opened.path || []).at(-1);
      const outside = prefix ? (card.inner_edges || []).filter((edge) =>
        (edge.source === prefix || edge.source.startsWith(`${prefix}.`)) !==
        (edge.target === prefix || edge.target.startsWith(`${prefix}.`))) : [];
      const outNote = outside.length ? `<p>${outside.length} connections leave this folder, including ${outside.filter((edge) => edge.state === "violation").length} violations. Use the breadcrumb to inspect those crossings.</p>` : "";
      const ownerNote = owner.navigation_only
        ? "These modules have no unique declared owner. This view is navigation only and has no component verdict. "
        : "";
      return `<div class="kicker">Inside</div><h2>${esc(prefix || opened.inside || opened.component)}</h2><p>${ownerNote}Folders follow physical package names; they are not declared architecture boundaries. Connections crossing visible folders are summed. Open a folder to inspect its contents; a red connection still marks a broken rule.</p>${statBlock()}${outNote}${heaviestBlock()}`;
    }
    return `<div class="kicker">Level 2 · components</div><h2>Component flow</h2><p>Declared components are shown with their observed imports. “Unassigned modules” is navigation only and does not imply a component boundary or verdict. Select a box or connection for evidence; select a box again to open its physical module view.</p>${statBlock()}${heaviestBlock()}`;
  }

  function moduleTree(component, path = []) {
    const cards = cardLevel(component, path).components;
    if (!cards.length) return '<p class="empty">No modules observed.</p>';
    return `<ul class="module-tree">${cards.map((card) => card.folder
      ? `<li><details><summary>${esc(card.display)} <small>${card.modules.length} modules · ${card.import_sites} import sites${card.internal_violation ? " · contains violation" : ""}</small></summary>${moduleTree(component, [...path, card.label])}</details></li>`
      : `<li><code>${esc(card.display)}</code>${card.public === null ? "" : ' <span class="interface-label">provided</span>'}</li>`).join("")}</ul>`;
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
      if (component.library) {
        const rules = scopeRules(component);
        inspector.innerHTML = `<div class="kicker">External library</div><h2>${esc(component.display)}</h2>
          <dl class="kv"><dt>Observed import sites</dt><dd>${component.import_sites}</dd>
          <dt>Scope rules</dt><dd>${rules.length}</dd>${relations}</dl>${scopeRuleList(component)}`;
        return;
      }
      if (opened && opened.module) {
        inspector.innerHTML = `<div class="kicker">Symbol</div><h2>${esc(component.label)}</h2>
          <dl class="kv"><dt>Kind</dt><dd>${esc(component.kind || "symbol")}</dd>
          <dt>Outside</dt><dd>${component.public === null ? "not imported elsewhere" : "imported by another module"}</dd>
          ${relations}</dl>
          ${(component.members || []).length ? `<h3>Methods</h3><ul class="plain">${component.members.map((m) => `<li><code>${esc(m)}</code></li>`).join("")}</ul>` : ""}`;
        return;
      }
      if (opened) {
        const owner = componentByLabel.get(opened.component);
        const card = opened.inside ? (owner.inside.components || []).find((item) => item.label === opened.inside) : owner;
        inspector.innerHTML = `<div class="kicker">${component.folder ? "Physical package" : "Module"}</div><h2>${esc(component.label)}</h2>
          <dl class="kv"><dt>Modules</dt><dd>${component.modules.length}</dd><dt>Import sites touching group</dt><dd>${component.import_sites || 0}</dd>${relations}</dl>
          ${component.folder ? moduleTree({ ...card, modules: component.modules, inner_edges: card.inner_edges }, [...(opened.path || []), component.label]) : `<p>${component.openable ? "Select again to inspect its symbols." : "No symbols recorded."}</p>`}`;
        return;
      }
      if (component.navigation_only) {
        inspector.innerHTML = `<div class="kicker">Module inventory · navigation only</div><h2>${esc(component.display || component.label)}</h2>
          <p>These modules have no unique declared owner. This view does not add a component boundary, permission or verdict.</p>
          <dl class="kv"><dt>Modules</dt><dd>${component.modules.length}</dd>${relations}</dl>
          <h3>Physical module tree</h3>${moduleTree(component)}`;
        return;
      }
      const required = component.requires || [];
      inspector.innerHTML = `<div class="kicker">Component</div><h2>${esc(component.label)}</h2>
        <dl class="kv"><dt>Modules</dt><dd>${component.modules.length}</dd>
        ${relations}</dl>
        <h3>Physical module tree</h3>${moduleTree(component)}
        <details><summary>Provided interface · ${component.public === null ? "not declared" : `${component.public.length} entries`}</summary>${
          component.public === null
            ? '<p class="empty">No interface boundary declared; this is not proof of a clean public API.</p>'
            : `<ul class="plain">${component.public.map((p) => `<li><code>${esc(p)}</code></li>`).join("") || '<li class="empty">Declared empty.</li>'}</ul>`
        }</details><details><summary>Required components · ${required.length}</summary><ul class="plain">${required.map((entry) => `<li><code>${esc(entry.component)}</code>${entry.through && entry.through.length ? ` through <code>${entry.through.map(esc).join(", ")}</code>` : " · interface not narrowed"}${entry.rationale ? ` — ${esc(entry.rationale)}` : ""}${entry.decided_by ? ` (${esc(entry.decided_by)})` : ""}</li>`).join("")}</ul></details>`;
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
      <dl class="kv"><dt>Verdict</dt><dd>${esc(edge.state)}</dd><dt>Import sites</dt><dd>${edge.import_sites}</dd>${edge.library ? "" : `<dt>Interface names</dt><dd>${edge.names.length}</dd>`}</dl>
      ${edge.library ? `<h3>External library scope</h3>${scopeRuleList(edge.scope)}` : ""}
      ${edge.requirement && edge.requirement.component ? `<p>Declared dependency: ${edge.requirement.through && edge.requirement.through.length ? `through <code>${edge.requirement.through.map(esc).join(", ")}</code>` : "interface not narrowed"}${edge.requirement.rationale ? ` — ${esc(edge.requirement.rationale)}` : ""}${edge.requirement.decided_by ? ` (${esc(edge.requirement.decided_by)})` : ""}.</p>` : ""}
      ${(edge.sites || []).length ? `<h3>Example import sites</h3><ul class="plain">${edge.sites.map((site) => `<li><code>${esc(site)}</code></li>`).join("")}</ul>` : ""}
      ${
        edge.rule_ids.length
          ? `<h3>Broken rules</h3><ul class="plain">${edge.rule_ids.map((r) => { const rule = (DATA.rules || {})[r] || {}; return `<li class="violation-card"><code>${esc(r)}</code>${rule.rationale ? ` — ${esc(rule.rationale)}` : ""}${rule.decided_by ? ` (${esc(rule.decided_by)})` : ""}</li>`; }).join("")}</ul>`
          : ""
      }
      ${edge.names.length ? `<h3>Names used across the boundary</h3>${names}` : ""}`;
  }

  function legendSwatch(state) {
    const swatch = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    swatch.setAttribute("class", "flow-legend-swatch");
    swatch.setAttribute("viewBox", "0 0 28 10");
    // The swatch draws the same ratio the diagram does, at the width it is drawn here, so the
    // legend keeps explaining the pattern the reader actually sees.
    const width = 2;
    swatch.appendChild(
      el(
        "g",
        { class: `edge ${state}` },
        el("path", { class: "line", d: "M1,5 H27", "stroke-width": String(width), ...dashFor(state, width) }),
      ),
    );
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
    const libraryHint = document.createElement("span");
    libraryHint.className = "flow-legend-item";
    libraryHint.textContent = "«library» and a dashed teal arrow: observed use of a scoped external dependency";
    legend.appendChild(libraryHint);
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
      const screenX = event.clientX - dragState.x;
      const screenY = event.clientY - dragState.y;
      // The card moves in diagram units, but the tap threshold is a distance the hand makes,
      // so it is measured on screen. Dividing by the zoom turned an 8px wobble into 20 units
      // at scale 0.63 and rejected every touch as a drag.
      dragState.moved = Math.max(dragState.moved, Math.hypot(screenX, screenY));
      const dx = screenX / transform.k;
      const dy = screenY / transform.k;
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
  // A press that barely moved is a tap, not a drag. A mouse sits still, a finger never does:
  // three pixels rejected every touch as a drag, which left the lower levels unreachable on a
  // phone. The slack follows the pointer that made the press.
  const TAP_SLACK = { mouse: 3, pen: 6, touch: 12 };
  const endPointer = () => {
    // The kind is read from the press that started the gesture, not from the release: one
    // source for one fact, and pointer capture can hand the release a different shape.
    const slack = dragState ? (TAP_SLACK[dragState.pointerType] ?? TAP_SLACK.touch) : 0;
    const tapped = dragState && dragState.moved <= slack ? dragState.label : null;
    panState = null;
    dragState = null;
    if (tapped !== null) selectCard(tapped);
  };
  // A cancelled pointer is the browser taking the gesture away, never a tap: only forget it.
  const cancelPointer = () => {
    panState = null;
    dragState = null;
  };
  svg.addEventListener("pointerup", endPointer);
  svg.addEventListener("pointercancel", cancelPointer);
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
  // Clearing belongs to the background alone. A tap on a card is handled in endPointer, and
  // the browser then sends the click along anyway; since the card no longer carries a click
  // handler to stop it, that click reached this one and wiped the selection the tap had just
  // made. The first tap appeared to work and every following one did nothing.
  svg.addEventListener("click", (event) => {
    if (!selected) return;
    const path = event.composedPath ? event.composedPath() : [];
    const onCard = path.some(
      (node) => node.classList && (node.classList.contains("node") || node.classList.contains("hit")),
    );
    if (onCard) return;
    selected = null;
    render();
  });

  // Where one press of Back returns to, named for the level the viewer is standing on.
  function backLabel() {
    if (opened.module) return `Back to ${(opened.path || []).at(-1) || opened.inside || opened.component}`;
    if (opened.path && opened.path.length) return `Back to ${opened.path.length > 1 ? opened.path[opened.path.length - 2] : opened.inside || opened.component}`;
    if (opened.inside) return `Back to ${opened.component}`;
    return "Back to components";
  }

  function crumbs() {
    const items = [{ label: "Components", state: null }];
    if (!opened) return items;
    items.push({ label: opened.component, state: { component: opened.component, path: [] } });
    if (opened.inside) items.push({ label: opened.inside, state: { component: opened.component, inside: opened.inside, path: [] } });
    (opened.path || []).forEach((name, index) => items.push({ label: name.split(".").pop(), state: { component: opened.component, ...(opened.inside ? { inside: opened.inside } : {}), path: opened.path.slice(0, index + 1) } }));
    if (opened.module) items.push({ label: opened.module.split(".").pop(), state: opened });
    return items;
  }

  function updateNavigation() {
    backButton.hidden = !opened;
    if (opened) backButton.textContent = backLabel();
    breadcrumb.textContent = "";
    crumbs().forEach((item, index, all) => {
      if (index) breadcrumb.append(" / ");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.label;
      button.disabled = index === all.length - 1;
      button.addEventListener("click", () => {
        opened = item.state;
        selected = null;
        positions = {};
        defaultThreshold();
        render();
        fit(false);
      });
      breadcrumb.appendChild(button);
    });
  }

  function defaultThreshold() {
    const counts = level().edges.filter((edge) => edge.state !== "violation")
      .map((edge) => weight(edge)).sort((a, b) => b - a);
    const maximum = counts[0] || 1;
    thresholdInput.max = String(maximum);
    thresholdInput.value = String(opened && counts.length > 12 ? counts[11] : 0);
  }

  function enter(label) {
    if (!opened) {
      opened = { component: label, path: [] };
    } else if (opened.inside || !componentByLabel.get(opened.component).inside) {
      const card = level().components.find((c) => c.label === label);
      opened = card && card.folder
        ? { ...opened, path: [...(opened.path || []), label] }
        : { ...opened, module: card?.opensModule || label };
    } else {
      // On an inside level a card is a sub-component, except the one the contract left
      // unowned, which opens as the module it is (AD-34).
      const card = level().components.find((c) => c.label === label);
      opened = card && card.opensModule
        ? { component: opened.component, module: card.opensModule, path: [] }
        : { component: opened.component, inside: label, path: [] };
    }
    selected = null;
    positions = {};
    defaultThreshold();
    render();
    fit(false);
  }

  // One step back per press: a module returns to what held it, a sub-component to its
  // component, a component to the overview.
  function leave() {
    if (!opened) return;
    const history = crumbs();
    opened = history[history.length - 2].state;
    selected = null;
    positions = {};
    defaultThreshold();
    render();
    fit(false);
  }

  backButton.addEventListener("click", leave);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") leave();
  });

  thresholdInput.addEventListener("input", () => {
    positions = {};
    render();
    fit(false);
  });
  violationsOnly.addEventListener("change", () => {
    if (violationsOnly.checked && selected && selected.type === "edge") {
      const edge = level().edges.find((item) => edgeKey(item) === selected.key);
      if (edge && edge.state !== "violation") selected = null;
    }
    positions = {};
    render();
    fit(false);
  });
  // Fit used to move the camera only, which left a hand-dragged card where it was and offered
  // no way back to the computed arrangement.
  fitButton.addEventListener("click", () => {
    positions = {};
    render();
    fit(true);
  });
  violationFocus.hidden = false;

  renderLegend();
  defaultThreshold();
  render();
  fit(false);
  window.addEventListener("resize", () => fit(false));
})();
