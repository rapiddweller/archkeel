"use strict";
// One report model, scene projection and UML renderer for every architecture view.
(function () {
  const root = document.getElementById("flow");
  const dataNode = document.getElementById("flow-data");
  if (!root || !dataNode) return;
  const flowHeading = document.getElementById("flow-heading");
  flowHeading.tabIndex = -1;
  const DATA = JSON.parse(dataNode.textContent);
  const graphIndexes = new WeakMap();
  if (DATA.schema_version !== "1.0.0") {
    root.textContent = "Unsupported architecture report schema.";
    return;
  }
  let positions = {}, diagramOrigin = null, sizedPositions = positions;
  let scrollRemainderX = 0, scrollRemainderY = 0;
  let viewMode = "diagram", renderedScene = null, focusLabel = null, relationshipKind = null, elementKind = null;
  let transform = { k: 1 }, umlPath = [], umlSelection = null, scopeNotice = null;
  let dragState = null, panState = null, expansionRestore = null;
  let lastPointerTap = null, skipSvgClick = false;
  const viewStates = new Map(), navigationHistory = new Map();
  const CARD = { w: 200, h: 92 };
  const cardHeights = new Map();
  const GAP = 34;
  const ROW_GAP = 90;
  const FRAME_HEADER_HEIGHT = 53;
  const TARGET_RESIDUAL_GAP = 20;
  let TARGET_FRAME_HEADER_ALLOWANCE = FRAME_HEADER_HEIGHT;
  const LANE_GAP = 11;
  const ROUTING_WARNING = "Renderer layout warning: no clear route around a card or frame header; architectural status is unchanged.";

  // The one place an EdgeState maps to a human label. Edge and chip elements already take their
  // color and dash pattern from the CSS class `edge ${state}` / `chip ${state}` (see
  // archkeel-report.css), so the legend swatches below reuse those same classes instead of a
  // second, hand-written color/dash list.

  const svg = root.querySelector(".flow-graph");
  for (const kind of ["calls", "imports", "references", "creates", "instance_of"]) {
    const marker = svg.querySelector("#flow-arrow-declared").cloneNode(true);
    marker.id = `flow-arrow-uml-${kind}`;
    marker.querySelector("path").style.stroke = `var(--uml-${kind})`;
    svg.querySelector("defs").appendChild(marker);
  }
  const canvas = root.querySelector(".flow-canvas");
  const viewport = root.querySelector(".flow-viewport");
  const edgeLayer = viewport.querySelector(".flow-edges");
  const frameLayer = viewport.querySelector(".flow-frames");
  const chipLayer = viewport.querySelector(".flow-chips");
  const nodeLayer = viewport.querySelector(".flow-nodes");
  const emptyLayer = viewport.querySelector(".flow-empty");
  const inspector = root.querySelector(".flow-inspector");
  inspector.id = "flow-inspector";
  const inspectorContent = inspector.querySelector(".flow-inspector-content");
  const toolbar = root.querySelector(".flow-toolbar");
  const filters = root.querySelector(".flow-filters");
  const legendPanel = root.querySelector(".flow-legend-panel");
  const compactControls = window.matchMedia("(max-width: 900px)");
  filters.open = !compactControls.matches;
  legendPanel.open = !compactControls.matches;
  compactControls.addEventListener("change", () => {
    filters.open = !compactControls.matches;
    legendPanel.open = !compactControls.matches;
  });
  const legend = root.querySelector(".flow-legend");
  const violationFocus = root.querySelector(".flow-violation-focus");
  const violationsOnly = root.querySelector(".flow-violations-only");
  const fitButton = root.querySelector(".flow-arrange");
  const overviewButton = root.querySelector(".flow-fit-overview");
  const zoomOutButton = root.querySelector(".flow-zoom-out");
  const zoom100Button = root.querySelector(".flow-zoom-100");
  const zoomInButton = root.querySelector(".flow-zoom-in");
  const zoomValue = root.querySelector(".flow-zoom-value");
  const resetFiltersButton = root.querySelector(".flow-reset-filters");
  const filterStatus = root.querySelector(".flow-filter-status");
  const focusInput = root.querySelector(".flow-focus");
  const elementKindControl = document.createElement("label");
  elementKindControl.className = "flow-diagram-control flow-diagram-filter flow-graph-filter";
  elementKindControl.append("Element kind");
  const elementKindInput = document.createElement("select");
  elementKindInput.className = "flow-focus";
  elementKindInput.setAttribute("aria-label", "Element kind");
  elementKindControl.appendChild(elementKindInput);
  focusInput.closest("label").after(elementKindControl);
  const backButton = root.querySelector(".flow-back");
  const breadcrumb = root.querySelector(".flow-breadcrumb");
  const viewButtons = root.querySelectorAll("[data-flow-view]");
  const alternative = root.querySelector(".flow-alternative");
  const openSelectedButton = root.querySelector(".flow-open-selected");
  const fullscreenButton = root.querySelector(".flow-fullscreen");
  const expandStatus = root.querySelector(".flow-expand-status");
  let pendingAlternativeFocus = null;
  let targetDetailsOpen = false;
  const detailsToggle = document.createElement("button");
  detailsToggle.type = "button";
  detailsToggle.className = "flow-fit flow-details-toggle";
  detailsToggle.dataset.flowDetailsToggle = "";
  detailsToggle.setAttribute("aria-controls", inspector.id);
  detailsToggle.setAttribute("aria-expanded", "false");
  detailsToggle.textContent = "Details";
  toolbar.appendChild(detailsToggle);
  let memberPreviews = false;
  const memberPreviewsButton = document.createElement("button");
  memberPreviewsButton.type = "button";
  memberPreviewsButton.className = "flow-fit flow-member-previews";
  memberPreviewsButton.textContent = "Member previews";
  memberPreviewsButton.setAttribute("aria-pressed", "false");
  memberPreviewsButton.hidden = true;
  toolbar.appendChild(memberPreviewsButton);
  memberPreviewsButton.addEventListener("click", () => {
    memberPreviews = !memberPreviews;
    memberPreviewsButton.setAttribute("aria-pressed", String(memberPreviews));
    positions = {};
    // Saved coordinates belong to the previous card sizes, not to the navigation scope.
    for (const state of [...viewStates.values(), ...[...navigationHistory.values()].flat()]) {
      state.positions = {};
    }
    render();
    fit();
  });

  const esc = (value) =>
    String(value).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  function el(tag, attrs, ...children) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    children.forEach((child) => node.appendChild(child));
    return node;
  }

  const sansFontFamily = getComputedStyle(document.documentElement)
    .getPropertyValue("--ck-font-sans").replace(/\s+/g, " ").trim();
  const monoFontFamily = getComputedStyle(document.documentElement)
    .getPropertyValue("--ck-font-mono").replace(/\s+/g, " ").trim();
  const measureCanvas = document.createElement("canvas");
  const measureText = measureCanvas.getContext("2d");

  const DASH_RATIOS = { violation: [2.4, 1.8], undecided: [0.55, 1.5], observed: [1.6, 1.4] };

  function setTargetDetails(open) {
    targetDetailsOpen = open;
    root.dataset.detailsOpen = String(open);
    detailsToggle.setAttribute("aria-expanded", String(open));
    detailsToggle.setAttribute("aria-label", "Details " + (open ? "open" : "closed"));
    inspector.hidden = !open;
  }

  function capturePointer(target, event) {
    try {
      target.setPointerCapture(event.pointerId);
    } catch {
      /* best-effort; pointermove/pointerup still drive the drag or pan via bubbling */
    }
  }

  function wrapText(value, maxWidth, font) {
    const text = String(value ?? "");
    measureText.font = font;
    const lines = [];
    let line = "";
    for (const word of text.split(/(\s+)/).filter(Boolean)) {
      if (/^\s+$/.test(word)) {
        line += word;
        continue;
      }
      const candidate = line + word;
      if (measureText.measureText(candidate).width <= maxWidth || !line.trim()) {
        if (measureText.measureText(candidate).width <= maxWidth) {
          line = candidate;
          continue;
        }
      } else {
        lines.push(line);
        line = "";
      }
      for (const character of word) {
        if (line && measureText.measureText(line + character).width > maxWidth) {
          lines.push(line);
          line = "";
        }
        line += character;
      }
    }
    if (line || !lines.length) lines.push(line);
    return lines;
  }

  function compactFrameName(scope, maxWidth) {
    const parts = String(scope ?? "").split(/[./]/).filter(Boolean);
    const name = parts.at(-1) || String(scope ?? "");
    const font = `600 15px ${sansFontFamily}`;
    measureText.font = font;
    if (measureText.measureText(name).width <= maxWidth) return name;
    const characters = Array.from(name);
    let low = 0;
    let high = characters.length;
    while (low < high) {
      const keep = Math.ceil((low + high) / 2);
      if (measureText.measureText(`${characters.slice(0, keep).join("")}…`).width <= maxWidth) {
        low = keep;
      } else high = keep - 1;
    }
    return `${characters.slice(0, low).join("")}…`;
  }

  function frameHeaderText(parent, role, name, x, y) {
    const roleText = el("text", {
      class: "target-frame-role",
      x: String(x),
      y: String(y - 18),
    });
    roleText.textContent = role;
    parent.appendChild(roleText);
    const nameText = el("text", {
      class: "target-frame-title",
      x: String(x),
      y: String(y),
    });
    nameText.textContent = name;
    parent.appendChild(nameText);
  }

  function createWrappedText(value, attrs, maxWidth, font, lineHeight) {
    const text = el("text", attrs);
    wrapText(value, maxWidth, font).forEach((line, index) => {
      const tspan = el("tspan", { x: attrs.x, dy: index ? String(lineHeight) : "0" });
      tspan.textContent = line;
      text.appendChild(tspan);
    });
    return text;
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

  function updateFullscreenState() {
    if (document.fullscreenElement === root) {
      root.dataset.expanded = "native";
      fullscreenButton.textContent = "Restore";
      expandStatus.hidden = true;
    } else if (root.dataset.expanded === "native") {
      delete root.dataset.expanded;
      fullscreenButton.textContent = "Fullscreen";
    }
  }

  function restoreExpansion() {
    if (root.dataset.expanded === "native") {
      document.exitFullscreen?.();
      return;
    }
    if (root.dataset.expanded !== "fallback") return;
    delete root.dataset.expanded;
    root.removeAttribute("aria-modal");
    root.removeAttribute("role");
    document.body.style.overflow = expansionRestore.bodyOverflow;
    window.scrollTo(expansionRestore.scrollX, expansionRestore.scrollY);
    for (const [element, inert] of expansionRestore.inert) element.inert = inert;
    const focus = expansionRestore.focus;
    expansionRestore = null;
    fullscreenButton.textContent = "Fullscreen";
    expandStatus.hidden = true;
    if (focus?.isConnected) focus.focus({ preventScroll: true });
  }

  function computeRanks(view, edges) {
    const rank = new Map(view.components.map((c) => [c.label, 0]));
    // Violated edges are excluded: a declared-rule violation is exactly the evidence that the
    // pair should not be read as forward architectural flow, so it must not drive layer depth.
    const forward = edges.filter((e) => e.state !== "violation"
      && rank.has(e.source) && rank.has(e.target));
    const incoming = new Map([...rank.keys()].map((id) => [id, 0]));
    const outgoing = groupBy(forward, (edge) => edge.source);
    forward.forEach((edge) => incoming.set(edge.target, incoming.get(edge.target) + 1));
    const ready = [...rank.keys()].filter((id) => incoming.get(id) === 0);
    for (let index = 0; index < ready.length; index += 1) {
      const source = ready[index];
      for (const edge of outgoing.get(source) || []) {
        rank.set(edge.target, Math.max(rank.get(edge.target), rank.get(source) + 1));
        incoming.set(edge.target, incoming.get(edge.target) - 1);
        if (incoming.get(edge.target) === 0) ready.push(edge.target);
      }
    }
    // A cycle cannot establish forward layout depth; its downstream nodes remain unranked too.
    incoming.forEach((count, id) => { if (count > 0) rank.set(id, null); });
    return rank;
  }

  function portX(node, index, count) {
    const inset = 24;
    const span = CARD.w - 2 * inset;
    const at = count === 1 ? span / 2 : (span * index) / (count - 1);
    return positions[node].x + inset + at;
  }

  function cardHeight(id) {
    return cardHeights.get(id) ?? CARD.h;
  }

  function measureUmlCards(nodes) {
    measureText.font = `600 14px ${sansFontFamily}`;
    CARD.w = Math.min(340, Math.max(200, ...nodes.map((node) =>
      Math.ceil(measureText.measureText(node.label).width) + 48)));
    cardHeights.clear();
    for (const node of nodes) {
      if (["method", "function", "attribute", "binding"].includes(node.kind)) {
        node.meta = compactUmlText(node.meta, `12px ${monoFontFamily}`);
      }
      for (const section of node.sections || []) {
        section.lines = section.lines.map((line) => compactUmlText(line));
      }
      const names = wrapText(node.label, CARD.w - 48, `600 14px ${sansFontFamily}`);
      const metadata = wrapText(node.meta, CARD.w - 32, `12px ${monoFontFamily}`);
      let height = Math.max(92, 42 + names.length * 18 + metadata.length * 14 + 10);
      if (node.sections?.length) height = Math.max(height,
        umlCompartments(node).at(-1).bottom + 12);
      cardHeights.set(node.id, height);
    }
    CARD.h = Math.max(92, ...cardHeights.values());
    TARGET_FRAME_HEADER_ALLOWANCE = FRAME_HEADER_HEIGHT;
  }

  function umlSymbol(kind) {
    const icon = el("g", { class: "uml-icon", "aria-hidden": "true",
      transform: `translate(${CARD.w - 29},11)` });
    if (kind === "component" || kind === "library") {
      icon.append(el("rect", { x: "5", y: "1", width: "15", height: "17" }),
        el("rect", { x: "0", y: "5", width: "7", height: "4" }),
        el("rect", { x: "0", y: "12", width: "7", height: "4" }));
    } else if (kind === "package") {
      icon.appendChild(el("path", { d: "M0,2 h8 l3,4 h13 v14 h-24 z" }));
    } else if (["module", "file"].includes(kind)) {
      icon.appendChild(el("path", { d: "M4,0 h11 l6,6 v16 h-17 z M15,0 v6 h6" }));
    } else if (kind === "interface") {
      icon.appendChild(el("circle", { cx: "11", cy: "10", r: "8" }));
    } else if (["class", "enum"].includes(kind)) {
      icon.append(el("rect", { x: "1", y: "0", width: "21", height: "23" }),
        el("path", { d: kind === "class" ? "M1,8 h21 M1,15 h21" : "M1,8 h21" }));
    } else if (["method", "function"].includes(kind)) {
      const glyph = el("text", { x: "0", y: "15" });
      glyph.textContent = kind === "method" ? "()" : "ƒ";
      icon.appendChild(glyph);
    }
    return icon.childElementCount ? icon : null;
  }

  function drawUmlCard(node) {
    const position = positions[node.id];
    const group = el("g", {
      class: `node uml-card ${node.kind}`, transform: `translate(${position.x},${position.y})`,
      tabindex: "0", role: "button", "aria-label": node.label,
      "data-uml-id": node.id, "data-uml-kind": node.kind, "data-label": node.label,
    });
    group.appendChild(el("rect", {
      class: "card", width: String(CARD.w), height: String(cardHeight(node.id)),
      rx: ["class", "interface", "enum"].includes(node.kind) ? "2" : "8",
    }));
    if (node.violation) group.appendChild(el("rect", {
      class: "tick violated", width: "3", height: String(cardHeight(node.id) - 24), x: "0", y: "12",
    }));
    const kind = el("text", { class: "stereotype", x: "16", y: "19" });
    kind.textContent = `«${node.kind === "enum" ? "enumeration" : node.kind}»${node.outside ? " · outside" : ""}`;
    group.appendChild(kind);
    const name = createWrappedText(node.label, { class: "label", x: "16", y: "37" },
      CARD.w - 48, `600 14px ${sansFontFamily}`, 18);
    group.appendChild(name);
    const nameLines = wrapText(node.label, CARD.w - 48, `600 14px ${sansFontFamily}`).length;
    group.appendChild(createWrappedText(node.meta, {
      class: "meta", x: "16", y: String(42 + nameLines * 18),
    }, CARD.w - 32, `12px ${monoFontFamily}`, 14));
    for (const section of umlCompartments(node)) {
      group.appendChild(el("path", { class: "uml-divider", d: `M0,${section.top} H${CARD.w}` }));
      const heading = el("text", { class: "uml-compartment-title", x: "12", y: String(section.top + 15) });
      heading.textContent = section.label;
      group.appendChild(heading);
      let y = section.top + 32;
      for (const line of section.lines) {
        group.appendChild(createWrappedText(line, { class: "uml-member", x: "12", y: String(y) },
          CARD.w - 24, `11px ${monoFontFamily}`, 14));
        y += wrapText(line, CARD.w - 24, `11px ${monoFontFamily}`).length * 14;
      }
    }
    const symbol = umlSymbol(node.kind);
    if (symbol) group.appendChild(symbol);
    const title = el("title");
    title.textContent = node.tooltip;
    group.appendChild(title);
    return group;
  }

  function umlCompartments(node) {
    let top = 46 + wrapText(node.label, CARD.w - 48, `600 14px ${sansFontFamily}`).length * 18
      + wrapText(node.meta, CARD.w - 32, `12px ${monoFontFamily}`).length * 14;
    return (node.sections || []).map((section) => {
      const bottom = top + 30 + section.lines.reduce((height, line) =>
        height + wrapText(line, CARD.w - 24, `11px ${monoFontFamily}`).length * 14, 0);
      const compartment = { ...section, top, bottom };
      top = bottom + 8;
      return compartment;
    });
  }

  function drawUmlFrame(frame, singleRoot) {
    const box = frame.bounds;
    const group = el("g", {
      class: `node uml-frame${singleRoot && !frame.parent ? " package-overview" : ""}`,
      tabindex: "0", role: "button", "data-uml-id": frame.id, "data-uml-kind": "package",
      "data-label": frame.label,
    });
    group.appendChild(el("rect", { class: "target-frame", x: String(box.left),
      y: String(box.top), width: String(box.right - box.left),
      height: String(box.bottom - box.top), rx: "8" }));
    group.appendChild(el("rect", { class: "target-frame-header-hit", x: String(box.left),
      y: String(box.top), width: String(box.right - box.left),
      height: String(box.header), rx: "8" }));
    group.appendChild(el("path", { class: "uml-package", "aria-hidden": "true",
      d: `M${box.left + 14},${box.top + 15} h12 l4,5 h16 v18 h-32 z` }));
    const name = compactFrameName(frame.scope, box.right - box.left - 70);
    frameHeaderText(group, "«package»", name, box.left + 56, box.top + 37);
    group.setAttribute("aria-label", frame.tooltip);
    const title = el("title");
    title.textContent = frame.tooltip;
    group.appendChild(title);
    return group;
  }

  function umlRoutes(scene) {
    const frames = Object.fromEntries(scene.frames.map((frame) => [frame.id, frame.bounds]));
    const edges = scene.edges;
    const callFan = edges.length > 0 && edges.every((edge) =>
      edge.relationshipKind === "calls" && edge.source === edges[0].source);
    // Both directions share a card side; separate degree tables would reuse its ports.
    const endpoints = edges.flatMap((edge) => {
      const upward = positions[edge.target].y < positions[edge.source].y;
      const sameRow = positions[edge.source].y === positions[edge.target].y;
      return [
        { edge, end: "source", node: edge.source, other: edge.target,
          side: upward ? "top" : "bottom" },
        { edge, end: "target", node: edge.target, other: edge.source,
          side: upward || sameRow ? "bottom" : "top" },
      ];
    });
    const ports = groupBy(endpoints, (port) => `${port.node}:${port.side}`);
    ports.forEach((ports) => ports.sort((a, b) => {
      const ax = positions[a.other].x - positions[a.node].x;
      const bx = positions[b.other].x - positions[b.node].x;
      // Deeper callees need the outer ports to pass around the nearer row.
      const depth = callFan && a.end === "source" && b.end === "source" && ax * bx > 0
        ? Math.sign(ax) * (Math.abs(positions[a.other].y - positions[a.node].y)
          - Math.abs(positions[b.other].y - positions[b.node].y)) : 0;
      return depth || ax - bx || a.edge.id.localeCompare(b.edge.id) || a.end.localeCompare(b.end);
    }));
    const lanes = groupBy(edges, laneKey);
    // Outer targets first reduces crossings between one caller's outgoing lines.
    lanes.forEach((edges) => edges.sort((a, b) => positions[a.source].x - positions[b.source].x
      || Math.abs(positions[b.target].x - positions[b.source].x)
        - Math.abs(positions[a.target].x - positions[a.source].x)
      || positions[a.target].x - positions[b.target].x));
    const routes = [];
    const occupied = { vertical: new Map(), horizontal: new Map(), clearance: new Map(), callFan };
    edges.forEach((edge, index) => {
      const source = endpoints[index * 2], target = endpoints[index * 2 + 1];
      const out = ports.get(`${source.node}:${source.side}`);
      const into = ports.get(`${target.node}:${target.side}`);
      const lane = lanes.get(laneKey(edge));
      const route = routeFor(edge, out.indexOf(source), into.indexOf(target), out.length, into.length,
        laneOffsetFor(edge, lanes), protectedFrameHeaders(frames), frames, occupied, lane.indexOf(edge));
      routes.push({ edge, ...route });
      for (let i = 1; i < route.points.length; i += 1) {
        const [ax, ay] = route.points[i - 1], [bx, by] = route.points[i];
        const vertical = ax === bx;
        if (!vertical && ay !== by) continue;
        const axis = vertical ? occupied.vertical : occupied.horizontal;
        const at = vertical ? ax : ay;
        const key = Math.floor(at / LANE_GAP);
        if (!axis.has(key)) axis.set(key, []);
        axis.get(key).push({ at,
          start: Math.min(vertical ? ay : ax, vertical ? by : bx),
          end: Math.max(vertical ? ay : ax, vertical ? by : bx) });
      }
    });
    return routes;
  }

  function drawUmlEdge(edge, route) {
    edge.routingWarning = Boolean(route.routingWarning);
    const warning = edge.routingWarning ? ` ${ROUTING_WARNING}` : "";
    const group = el("g", { class: `edge ${edge.state}`, "data-uml-id": edge.id,
      "data-uml-kind": edge.kind, "data-uml-source": edge.source, "data-uml-target": edge.target });
    const line = el("path", { class: "line", d: route.d, "stroke-width": "2",
      ...(edge.state !== "declared" ? dashFor(edge.state, 2) : {}) });
    const title = el("title");
    title.textContent = edge.tooltip + warning;
    line.appendChild(title);
    const hit = el("path", { class: "hit", d: route.d, tabindex: "0", role: "button",
      "aria-label": edge.tooltip + warning,
      ...(route.routingWarning ? { "data-route-warning": "header-overlap" } : {}) });
    hit.appendChild(title.cloneNode(true));
    group.appendChild(line);
    if (edge.state !== "declared") group.appendChild(el("path", { class: "pulse", d: route.d }));
    group.appendChild(hit);
    if (edge.relationshipKind) {
      group.classList.add("architecture-edge");
      group.dataset.relationshipKind = edge.relationshipKind;
      line.style.strokeDasharray = edge.relationshipKind === "inherits" ? "none" : "6 4";
      if (["inherits", "realizes"].includes(edge.relationshipKind)) {
        line.style.markerEnd = "url(#uml-triangle)";
      } else if (!["violation", "undecided"].includes(edge.state)
        && svg.querySelector(`#flow-arrow-uml-${edge.relationshipKind}`)) {
        line.style.markerEnd = `url(#flow-arrow-uml-${edge.relationshipKind})`;
      } else if (edge.state === "declared") line.style.markerEnd = "url(#flow-arrow-declared)";
    }
    return { group, line, hit };
  }

  function renderUmlScene(scene, bindings) {
    renderedScene = scene;
    frameLayer.textContent = "";
    nodeLayer.textContent = "";
    edgeLayer.textContent = "";
    chipLayer.textContent = "";
    const singleRoot = scene.frames.filter((frame) => !frame.parent).length === 1;
    for (const frame of scene.frames) {
      const group = drawUmlFrame(frame, singleRoot);
      frameLayer.appendChild(group);
      bindings.frame(group, frame);
    }
    const routes = umlRoutes(scene);
    for (const route of routes) {
      const drawn = drawUmlEdge(route.edge, route);
      edgeLayer.appendChild(drawn.group);
      Object.assign(route, drawn);
      bindings.edge(drawn, route);
    }
    for (const node of scene.nodes) {
      if (!positions[node.id]) continue;
      const group = drawUmlCard(node);
      nodeLayer.appendChild(group);
      bindings.node(group, node);
    }
    return routes;
  }

  function laneKey(edge) {
    return [positions[edge.source].y, positions[edge.target].y].sort((a, b) => a - b).join(":");
  }

  function laneOffsetFor(edge, lanes) {
    const lane = lanes.get(laneKey(edge));
    const index = lane.indexOf(edge);
    if (positions[edge.source].y === positions[edge.target].y) return index * LANE_GAP;
    return (index - (lane.length - 1) / 2) * LANE_GAP;
  }

  function routePointsClear(points, headers, padding) {
    for (let index = 1; index < points.length; index += 1) {
      const [x1, y1] = points[index - 1];
      const [x2, y2] = points[index];
      for (const header of headers) {
        const left = header.left - padding;
        const right = header.right + padding;
        const top = header.top - padding;
        const bottom = header.bottom + padding;
        if (x1 === x2 && x1 > left && x1 < right
            && Math.max(y1, y2) > top && Math.min(y1, y2) < bottom) return false;
        if (y1 === y2 && y1 > top && y1 < bottom
            && Math.max(x1, x2) > left && Math.min(x1, x2) < right) return false;
      }
    }
    return true;
  }

  function orthogonalPath(points) {
    return points.map(([x, y], index) => `${index ? "L" : "M"}${x},${y}`).join(" ");
  }

  function protectedFrameHeaders(bounds) {
    return Object.values(bounds).map((frame) => ({
      left: frame.left,
      right: frame.right,
      top: frame.top,
      bottom: frame.top + frame.header,
    }));
  }

  function routeFor(
    edge, outIndex, inIndex, outCount, inCount, laneOffset, headers, frames, occupied, laneIndex,
  ) {
    const sourceFrame = frames[edge.source];
    const targetFrame = frames[edge.target];
    const otherSourceX = positions[edge.target].x + CARD.w / 2;
    const otherTargetX = positions[edge.source].x + CARD.w / 2;
    const frameAnchor = (frame, otherX) => ({
      x: otherX < (frame.left + frame.right) / 2 ? frame.left : frame.right,
      y: frame.top + frame.header + 10,
    });
    const sourceAnchor = sourceFrame ? frameAnchor(sourceFrame, otherSourceX) : null;
    const targetAnchor = targetFrame ? frameAnchor(targetFrame, otherTargetX) : null;
    const sx = sourceAnchor?.x ?? portX(edge.source, outIndex, outCount);
    const tx = targetAnchor?.x ?? portX(edge.target, inIndex, inCount);
    const sPos = positions[edge.source];
    const tPos = positions[edge.target];
    const sameRow = !sourceFrame && !targetFrame && sPos.y === tPos.y;
    const sourceHeight = cardHeight(edge.source), targetHeight = cardHeight(edge.target);
    const sy = sourceAnchor?.y;
    const ty = targetAnchor?.y;
    const upward = (ty ?? tPos.y) < (sy ?? sPos.y);
    if (sameRow) {
      const sy = sPos.y + sourceHeight;
      const targetBottom = tPos.y + targetHeight;
      const drop = Math.max(sy, targetBottom) + 56 + laneOffset;
      const end = targetBottom;
      const points = [[sx, sy], [sx, drop], [tx, drop], [tx, end]];
      const direct = {
        d: orthogonalPath(points),
        mid: [(sx + tx) / 2, drop], end: [tx, end],
      };
      return routeAroundHeaders(direct, points, sx, sy, tx, end, headers, edge, frames, occupied, laneIndex);
    }
    const startY = sy ?? (upward ? sPos.y : sPos.y + sourceHeight);
    const endY = ty ?? (upward ? tPos.y + targetHeight : tPos.y);
    const my = (startY + endY) / 2 + laneOffset;
    const end = endY;
    const frameSideLead = (frame, anchor) => [
      anchor.x + (anchor.x === frame.left ? -14 : 14), anchor.y,
    ];
    const start = [sx, startY];
    const finish = [tx, end];
    const sourceLead = sourceAnchor ? frameSideLead(sourceFrame, sourceAnchor) : null;
    const targetLead = targetAnchor ? frameSideLead(targetFrame, targetAnchor) : null;
    const points = [
      start,
      ...(sourceLead ? [sourceLead, [sourceLead[0], my]] : [[sx, my]]),
      ...(targetLead ? [[targetLead[0], my], targetLead, finish] : [[tx, my], finish]),
    ];
    const direct = {
      d: orthogonalPath(points),
      mid: [(sx + tx) / 2, my],
      end: finish,
    };
    return routeAroundHeaders(direct, points, sx, startY, tx, end, headers, edge, frames, occupied, laneIndex);
  }

  function sharedRouteLength(points, occupied, limit = Infinity, clearance = LANE_GAP, avoidCrossings = false) {
    let total = 0;
    for (let i = 1; i < points.length; i += 1) {
      const [ax, ay] = points[i - 1], [bx, by] = points[i];
      const vertical = ax === bx;
      if (!vertical && ay !== by) continue;
      const axis = vertical ? occupied.vertical : occupied.horizontal;
      const at = vertical ? ax : ay;
      const start = Math.min(vertical ? ay : ax, vertical ? by : bx);
      const end = Math.max(vertical ? ay : ax, vertical ? by : bx);
      if (avoidCrossings) {
        const perpendicular = vertical ? occupied.horizontal : occupied.vertical;
        for (const segments of perpendicular.values()) {
          for (const segment of segments) {
            if (segment.at >= start && segment.at <= end && at >= segment.start && at <= segment.end) {
              total += LANE_GAP;
            }
            if (total > limit) return total;
          }
        }
      }
      const key = Math.floor(at / LANE_GAP);
      // Only nearby parallel segments can share a stretch.
      for (const bucket of [key - 1, key, key + 1]) {
        for (const segment of axis.get(bucket) || []) {
          if (Math.abs(at - segment.at) >= clearance) continue;
          const overlap = Math.min(end, segment.end) - Math.max(start, segment.start);
          if (overlap > 0) total += overlap;
          // Equality must finish scoring before the caller can compare tied candidates.
          if (total > limit) return total;
        }
      }
    }
    return total;
  }

  function routeAroundHeaders(direct, points, sx, sy, tx, end, headers, edge, frames, occupied, laneIndex) {
    const avoidCrossings = occupied.callFan;
    const cards = Object.entries(positions).filter(([id, position]) =>
      !frames[id] && Number.isFinite(position.x) && Number.isFinite(position.y));
    const cardBounds = cards.map(([id, position]) => ({
      left: position.x, right: position.x + CARD.w,
      top: position.y, bottom: position.y + cardHeight(id),
    }));
    if (routePointsClear(points, headers, 10)
        && routePointsClear(points, cardBounds, 0)
        && sharedRouteLength(points, occupied, 1, LANE_GAP, avoidCrossings) === 0) return { ...direct, points };
    const allLeft = Math.min(...[
      ...headers.map((header) => header.left),
      ...cards.map(([, position]) => position.x),
    ]);
    const allRight = Math.max(...[
      ...headers.map((header) => header.right),
      ...cards.map(([, position]) => position.x + CARD.w),
    ]);
    const gutters = [...new Set([
      ...headers.flatMap((header) => [header.left - 14, header.right + 14]),
      ...cardBounds.flatMap((card) => [card.left - GAP / 3, card.right + GAP / 3]),
      allLeft - 14, allRight + 14,
      allLeft - 14 - (laneIndex + 1) * LANE_GAP,
      allRight + 14 + (laneIndex + 1) * LANE_GAP,
    ])];
    const sourceCard = frames[edge.source] ? null : positions[edge.source];
    const targetCard = frames[edge.target] ? null : positions[edge.target];
    const sourceHeight = cardHeight(edge.source), targetHeight = cardHeight(edge.target);
    const sourceDirection = sourceCard ? Math.sign(sy - sourceCard.y - sourceHeight / 2)
      : Math.sign(points[1]?.[1] - sy) || Math.sign(end - sy) || 1;
    const endDirection = targetCard ? Math.sign(targetCard.y + targetHeight / 2 - end)
      : Math.sign(end - points.at(-2)?.[1]) || Math.sign(end - sy) || 1;
    // Separate arrival heights keep dependencies from sharing their final rail.
    const lead = 14 + Math.min(laneIndex * LANE_GAP, Math.max(0, Math.abs(end - sy) / 2 - 14));
    const normalSource = frames[edge.source]
      ? { point: [sx, sy], lead: points[1], axis: "horizontal" }
      : { point: [sx, sy], lead: [sx, sy + sourceDirection * 14], axis: "vertical" };
    const normalTarget = frames[edge.target]
      ? { point: [tx, end], lead: points.at(-2), axis: "horizontal" }
      : { point: [tx, end], lead: [tx, end - endDirection * lead], axis: "vertical" };
    if (normalTarget.axis === "vertical" && !routePointsClear(
        [normalTarget.lead, normalTarget.point], cardBounds, 0)) {
      normalTarget.lead = [tx, end - endDirection * 14];
    }
    const sourceBlocked = !routePointsClear(
      [normalSource.point, normalSource.lead], headers, 2,
    ) || !routePointsClear([normalSource.point, normalSource.lead], cardBounds, 0);
    const targetBlocked = !routePointsClear(
      [normalTarget.lead, normalTarget.point], headers, 2,
    ) || !routePointsClear([normalTarget.lead, normalTarget.point], cardBounds, 0);
    const sidePorts = (card, height, x) => ["left", "right"].map((side) => {
      const at = side === "left" ? card.x : card.x + CARD.w;
      const y = card.y + 14 + (height - 28) * (x - card.x) / CARD.w;
      return { point: [at, y], lead: [at + (side === "left" ? -14 : 14), y], axis: "horizontal" };
    });
    const clearance = occupied.clearance;
    const clearSegments = (points) => {
      for (let index = 1; index < points.length; index += 1) {
        const pair = [points[index - 1], points[index]];
        const key = `${pair[0][0]}:${pair[0][1]}:${pair[1][0]}:${pair[1][1]}`;
        if (!clearance.has(key)) clearance.set(key,
          routePointsClear(pair, headers, 2) && routePointsClear(pair, cardBounds, 0));
        if (!clearance.get(key)) return false;
      }
      return true;
    };
    let route = null, leastShared = Infinity, leastNearby = Infinity;
    // Preserve clear routes; change the source exit only when both target searches share a stretch.
    for (const [expanded, alternateSource] of [[false, false], [true, false], [false, true]]) {
      const sourcePorts = (sourceBlocked || alternateSource) && sourceCard
        ? sidePorts(sourceCard, sourceHeight, sx) : [normalSource];
      const distances = expanded
        ? Array.from({ length: Math.ceil((ROW_GAP - 14) / (LANE_GAP / 2)) }, (_, index) => 14 + index * LANE_GAP / 2)
        : [14, 14 + LANE_GAP];
      const offsets = expanded ? [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2] : [-1, 0, 1];
      const targetPorts = [
        ...(!targetBlocked ? [normalTarget, ...(normalTarget.axis === "vertical"
          ? distances.map((distance) => ({ ...normalTarget,
            lead: [tx, end - endDirection * distance] }))
            .filter((port) => port.lead[1] !== normalTarget.lead[1]) : [])] : []),
        ...(targetCard && (targetBlocked || expanded) ? sidePorts(targetCard, targetHeight, tx) : []),
      ];
      const sourceLanes = [...new Set([
        ...[normalSource.lead[1], normalTarget.lead[1]]
          .flatMap((y) => offsets.map((offset) => y + offset * LANE_GAP)),
        ...cards.flatMap(([id, position]) => [
          position.y - 14, position.y + cardHeight(id) + 14,
        ]).flatMap((y) => offsets.map((offset) => y + offset * LANE_GAP)),
        ...headers.flatMap((header) => [header.top - 14, header.bottom + 14]),
      ])];
      const candidateGutters = expanded ? [...new Set([...gutters,
        ...cardBounds.flatMap((card) => Array.from(
          { length: Math.floor(GAP / (LANE_GAP / 2)) - 1 }, (_, index) => {
            const offset = (index + 1) * LANE_GAP / 2;
            return [card.left - offset, card.right + offset];
          }).flat()),
      ])] : gutters;
      candidateGutters.sort((a, b) => Math.abs(sx - a) + Math.abs(tx - a)
        - Math.abs(sx - b) - Math.abs(tx - b));
      sourceLanes.sort((a, b) => Math.abs(sy - a) + Math.abs(end - a)
        - Math.abs(sy - b) - Math.abs(end - b));
      candidates: for (const source of sourcePorts) {
        const exits = sourceLanes.filter((laneY) => !(source.axis === "vertical"
          && (laneY - source.lead[1]) * sourceDirection < 0)
          && clearSegments([source.point, source.lead, [source.lead[0], laneY]]));
        for (const target of targetPorts) {
          const arrivals = candidateGutters.filter((x) => clearSegments([
            [x, target.lead[1]], target.lead, target.point,
          ]));
          for (const gutterX of arrivals) {
            for (const laneY of exits) {
              const points = [
                source.point, source.lead, [source.lead[0], laneY], [gutterX, laneY],
                [gutterX, target.lead[1]], target.lead, target.point,
              ];
              // Exits and arrivals already checked the first and last two segments.
              if (!clearSegments(points.slice(2, 5))) continue;
              const shared = sharedRouteLength(points, occupied, Math.max(1, leastShared), LANE_GAP / 2, avoidCrossings);
              if (shared > leastShared) continue;
              const nearby = sharedRouteLength(points, occupied,
                shared === leastShared ? Math.max(1, leastNearby) : Infinity, LANE_GAP, avoidCrossings);
              const length = points.slice(1).reduce((total, point, index) => total
                + Math.abs(point[0] - points[index][0]) + Math.abs(point[1] - points[index][1]), 0);
              if (shared < leastShared || nearby < leastNearby
                  || shared === leastShared && nearby === leastNearby && length < route.length) {
                route = { points, end: target.point, length };
                leastShared = shared; leastNearby = nearby;
              }
              if (shared === 0) break candidates;
            }
          }
        }
      }
      if (leastShared === 0) break;
    }
    if (!route) return { ...direct, points, routingWarning: true };
    return {
      d: orthogonalPath(route.points),
      mid: route.points[Math.floor(route.points.length / 2)],
      end: route.end,
      points: route.points,
    };
  }

  function dashFor(state, width) {
    const ratio = DASH_RATIOS[state];
    if (!ratio) return {};
    return { "stroke-dasharray": ratio.map((part) => (part * width).toFixed(2)).join(" ") };
  }

  function emphasizeUmlScene(focus, previewing = false) {
    if (!renderedScene) return;
    const related = new Set(focus?.type === "node" ? [focus.id] : []);
    const active = new Set();
    renderedScene.edges.forEach((edge) => {
      if (!focus || (focus.type === "edge" ? edge.id === focus.id
          : [edge.source, edge.target].includes(focus.id))) {
        active.add(edge.id);
        related.add(edge.source);
        related.add(edge.target);
      }
    });
    nodeLayer.querySelectorAll("[data-uml-id]").forEach((node) => {
      node.classList.toggle("dim", Boolean(focus && !related.has(node.dataset.umlId)));
      node.classList.toggle("related", Boolean(focus && related.has(node.dataset.umlId)));
      node.classList.toggle("preview", previewing && focus?.type === "node" && focus.id === node.dataset.umlId);
    });
    edgeLayer.querySelectorAll("[data-uml-id]").forEach((node) => {
      node.classList.toggle("dim", !active.has(node.dataset.umlId));
      node.classList.toggle("related", Boolean(focus && active.has(node.dataset.umlId)));
      node.classList.toggle("preview", Boolean(previewing && focus && active.has(node.dataset.umlId)));
    });
    chipLayer.querySelectorAll(".chip").forEach((node) => {
      node.classList.toggle("dim", !active.has(node.dataset.key));
    });
  }

  function layoutUmlScene(scene, preservePositions = false) {
    const graphNodes = scene.nodes;
    const containers = Object.fromEntries(scene.frames.map((frame) => [frame.id, frame]));
    const children = new Map(Object.keys(containers).map((id) => [id, []]));
    for (const [id, container] of Object.entries(containers)) {
      if (container.parent && children.has(container.parent)) children.get(container.parent).push(id);
    }
    children.forEach((ids) => ids.sort());
    const byId = new Map(graphNodes.map((node) => [node.id, node]));
    const frameIds = new Set(Object.keys(containers));
    const rankNodes = graphNodes.filter((node) => node.kind === "component");
    const residualRow = 1 + Math.max(0, ...rankNodes.map((node) => node.rank ?? 0));
    const step = CARD.w + GAP;
    let availableColumns = Math.max(1, Math.floor((canvas.clientWidth - 64 + GAP) / step));
    if (!scene.frames.length && graphNodes.length && canvas.clientHeight) {
      // Fit scales both axes; a viewport-width grid wastes most of a large overview's width.
      const totalHeight = graphNodes.reduce((sum, node) => sum + cardHeight(node.id) + 80, 0);
      const balancedColumns = Math.round(Math.sqrt(totalHeight / step
        * canvas.clientWidth / canvas.clientHeight));
      availableColumns = Math.max(availableColumns, balancedColumns);
    }
    const rowFor = (node) => node.rank === null ? residualRow
      : Number.isFinite(node.rank) ? node.rank : residualRow + 1;
    const itemsFor = (id) => [
      ...(containers[id].members || []).filter((member) => byId.has(member)),
    ];
    const laneItems = new Map(Object.keys(containers).sort().map((id) => [id, itemsFor(id)]));
    const containerMembers = new Set([...laneItems.values()].flat());
    const unplacedNodes = rankNodes.filter((node) => !containerMembers.has(node.id));
    laneItems.set("@unplaced", unplacedNodes.map((node) => node.id));
    const inventory = graphNodes.filter((node) =>
      !frameIds.has(node.id)
      && !containerMembers.has(node.id) && !rankNodes.includes(node),
    ).sort((left, right) => left.id.localeCompare(right.id));
    laneItems.set("@inventory", inventory.map((node) => node.id));
    const totalItems = [...laneItems.values()].reduce((sum, items) => sum + items.length, 0);
    const columnsByLane = new Map([...laneItems].map(([id, items]) =>
      [id, Math.max(1, Math.ceil(availableColumns * items.length / Math.max(1, totalItems)))]));
    const groupedRows = new Map();
    for (const [lane, identifiers] of laneItems) {
      const grouped = new Map();
      identifiers.forEach((identifier) => {
        const row = rowFor(byId.get(identifier));
        if (!grouped.has(row)) grouped.set(row, []);
        grouped.get(row).push(identifier);
      });
      for (const ids of grouped.values()) ids.sort((left, right) =>
        (byId.get(left).rank ?? 0) - (byId.get(right).rank ?? 0)
        || left.localeCompare(right));
      groupedRows.set(lane, grouped);
    }
    const laneOrder = [...laneItems.keys()];
    const rankedRows = [...new Set([...groupedRows.values()].flatMap((rows) => [...rows.keys()]))]
      .sort((left, right) => left - right);
    const rowHeights = new Map();
    const rowStarts = new Map();
    let nextRow = 0;
    rankedRows.forEach((rankRow) => {
      let rowHeight = 0;
      for (const lane of laneOrder) {
        const count = Math.ceil((groupedRows.get(lane).get(rankRow)?.length || 0)
          / columnsByLane.get(lane));
        rowHeight = Math.max(rowHeight, count);
      }
      rowStarts.set(rankRow, nextRow);
      rowHeights.set(rankRow, Math.max(1, rowHeight));
      nextRow += rowHeights.get(rankRow);
    });
    const rowsFor = (id) => {
      const rows = new Map();
      const maxColumns = columnsByLane.get(id);
      const grouped = groupedRows.get(id);
      [...grouped.keys()].sort((left, right) => left - right).forEach((rankRow) => {
        const ids = grouped.get(rankRow);
        const start = rowStarts.get(rankRow);
        for (let index = 0; index < ids.length; index += maxColumns) {
          rows.set(start + Math.floor(index / maxColumns), ids.slice(index, index + maxColumns));
        }
      });
      return rows;
    };
    const residualFrameDepth = (id, depth = 1) => Math.max(
      itemsFor(id).some((identifier) => {
        const node = byId.get(identifier);
        return node.kind === "component" && node.rank === null;
      }) ? depth : 0,
      ...children.get(id).map((child) => residualFrameDepth(child, depth + 1)),
    );
    const residualRowStart = rowStarts.get(residualRow);
    const residualFrameAllowance = Object.keys(containers)
      .filter((id) => !containers[id].parent)
      .reduce((depth, id) => Math.max(depth, residualFrameDepth(id)), 0)
      * TARGET_FRAME_HEADER_ALLOWANCE;
    const hasResidualComponents = rankNodes.some((node) => node.rank === null);
    const captionBand = hasResidualComponents ? TARGET_RESIDUAL_GAP + residualFrameAllowance : 0;
    const rowOffsets = new Map();
    let rowTop = 0;
    const laneRows = laneOrder.map(rowsFor);
    for (let row = 0; row < nextRow; row += 1) {
      rowOffsets.set(row, rowTop);
      const height = Math.max(92, ...laneRows.flatMap((rows) =>
        (rows.get(row) || []).map(cardHeight)));
      rowTop += height + 80;
    }
    const rowY = (row) => rowOffsets.get(row)
      + (row >= residualRowStart ? captionBand : 0);
    const laneWidth = (id) => {
      const rows = rowsFor(id);
      const columns = Math.max(children.get(id).length ? 0 : 1, ...[...rows].map(([, ids]) => ids.length));
      const childWidths = children.get(id).map(laneWidth);
      const ownWidth = columns * step;
      return ownWidth + childWidths.reduce((sum, width) => sum + width + GAP, 0);
    };
    const nextPositions = {};
    const frameBounds = {};
    const placed = new Set();

    const placeLane = (id, x, y = 0) => {
      const container = containers[id];
      const rows = rowsFor(id);
      const rowWidth = Math.max(children.get(id).length ? 0 : 1, ...[...rows].map(([, ids]) => ids.length));
      rows.forEach((items, row) => items.forEach((identifier, index) => {
        if (!placed.has(identifier)) {
          nextPositions[identifier] = preservePositions && positions[identifier]
            ? positions[identifier] : {
              x: x + (rowWidth - items.length) * step / 2 + index * step,
              y: y + rowY(row),
            };
        }
        placed.add(identifier);
      }));
      let childX = x + rowWidth * step;
      for (const child of children.get(id)) {
        placeLane(child, childX, y);
        childX += laneWidth(child) + GAP;
      }
      const descendants = [
        ...itemsFor(id).map((identifier) => {
          const position = nextPositions[identifier];
          return position ? { ...position, bottom: position.y + cardHeight(identifier) } : null;
        }),
        ...children.get(id).map((child) => frameBounds[child]),
      ].filter(Boolean);
      if (descendants.length) {
        const top = Math.min(...descendants.map((bounds) => bounds.top ?? bounds.y));
        const bottom = Math.max(...descendants.map((bounds) => bounds.bottom ?? bounds.y + CARD.h));
        const left = Math.min(...descendants.map((bounds) => bounds.left ?? bounds.x));
        const right = Math.max(...descendants.map((bounds) => bounds.right ?? bounds.x + CARD.w));
        frameBounds[id] = {
          left: left - 24,
          top: top - TARGET_FRAME_HEADER_ALLOWANCE,
          right: right + 24,
          bottom: bottom + 24,
          header: TARGET_FRAME_HEADER_ALLOWANCE,
        };
      } else {
        frameBounds[id] = {
          left: x - 24,
          top: -TARGET_FRAME_HEADER_ALLOWANCE,
          right: x + CARD.w + 24,
          bottom: 24,
          header: TARGET_FRAME_HEADER_ALLOWANCE,
        };
      }
      nextPositions[id] = { x: frameBounds[id].left + 12, y: frameBounds[id].top + 8 };
    };

    let x = 0;
    let y = 0;
    const roots = Object.keys(containers).filter((id) => !containers[id].parent).sort();
    for (const id of roots) {
      placeLane(id, x, y);
      x += laneWidth(id) + GAP;
    }
    const unplacedWidth = Math.max(0, ...[...rowsFor("@unplaced").values()].map((nodes) => nodes.length));
    rowsFor("@unplaced").forEach((nodes, row) => {
        nodes.forEach((identifier, column) => {
          nextPositions[identifier] = preservePositions && positions[identifier]
            ? positions[identifier] : {
              x: x + (unplacedWidth - nodes.length) * step / 2 + column * step,
              y: y + rowY(row),
            };
          placed.add(identifier);
        });
    });
    x += unplacedWidth * step;
    const inventoryWidth = Math.max(0, ...[...rowsFor("@inventory").values()].map((nodes) => nodes.length));
    rowsFor("@inventory").forEach((nodes, row) => {
      nodes.forEach((identifier, index) => {
        nextPositions[identifier] = preservePositions && positions[identifier]
          ? positions[identifier] : {
            x: x + (inventoryWidth - nodes.length) * step / 2 + index * step,
            y: y + rowY(row),
          };
      });
    });
    if (byId.has(scene.owner) && !nextPositions[scene.owner]) {
      nextPositions[scene.owner] = { x: 0, y: 0 };
    }

    const same = Object.keys(positions).length === Object.keys(nextPositions).length
      && Object.entries(nextPositions).every(([id, position]) =>
        positions[id]?.x === position.x && positions[id]?.y === position.y);
    const captionY = hasResidualComponents && residualRowStart !== undefined
      ? rowOffsets.get(residualRowStart) + 4 : null;
    return { positions: same ? positions : nextPositions, frameBounds, captionY };
  }

  function architectureEntities(graph) {
    if (graphIndexes.has(graph)) return graphIndexes.get(graph).entities;
    const entities = buildArchitectureEntities(graph);
    graphIndexes.set(graph, { entities, byId: new Map(entities.map((entity) => [entity.id, entity])) });
    return entities;
  }

  function buildArchitectureEntities(graph) {
    if (graph.origin !== "observed" || !DATA.target?.component_intents.length) return graph.entities;
    const owned = new Set((DATA.memberships || []).flatMap((item) => item.module_ids));
    const unassigned = graph.entities.filter((item) => item.kind === "module" && item.presence === "defined" && !owned.has(item.id));
    return [...graph.entities.filter((item) => item.kind !== "package" || unassigned.some((module) =>
      module.qualified_name === item.qualified_name || module.qualified_name.startsWith(item.qualified_name + "."))),
      ...DATA.target.entities.filter((item) => item.kind === "component")];
  }

  function architectureEntity(id, graph) {
    architectureEntities(graph);
    return graphIndexes.get(graph).byId.get(id);
  }

  function componentDepth(id) {
    const intent = DATA.target.component_intents.find((item) => item.component_id === id);
    return intent?.parent_id ? 1 + componentDepth(intent.parent_id) : 0;
  }

  function architectureHasInterior(entity, graph) {
    return architectureEntities(graph).some((child) => architectureParent(child, graph) === entity.id)
      || viewMode === "diff" && graph.origin === "declared" && DATA.observed
        && architectureEntities(DATA.observed).some((child) => architectureParent(child, DATA.observed) === entity.id)
      || graph.relationships.some((site) => site.source_id === entity.id && site.kind !== "owns");
  }

  function architectureParent(entity, graph) {
    if (entity.kind === "component") return (graph.origin === "observed" ? DATA.target : graph).component_intents
      .find((item) => item.component_id === entity.id)?.parent_id ?? entity.parent_id;
    if (graph.origin === "observed" && entity.kind === "module") {
      const memberships = (DATA.memberships || []).filter((item) => item.module_ids.includes(entity.id))
        .sort((left, right) => componentDepth(right.component_id) - componentDepth(left.component_id));
      const deepest = memberships.filter((item) => componentDepth(item.component_id)
        === componentDepth(memberships[0]?.component_id));
      if (deepest.length === 1) return deepest[0].component_id;
    }
    if (graph.origin === "observed" && entity.kind === "package") {
      // Namespace nesting is navigation, not a new lexical containment claim.
      const prefix = entity.qualified_name.split(".").slice(0, -1).join(".");
      return graph.entities.find((item) => item.kind === "package" && item.qualified_name === prefix)?.id ?? null;
    }
    return entity.parent_id;
  }

  function architectureLabel(entity, graph) {
    return (graph.origin === "observed" ? DATA.target?.component_intents || [] : graph.component_intents)
      .find((item) => item.component_id === entity.id)?.label
      || entity.qualified_name.split(".").at(-1);
  }

  function umlMember(entity, includeName = true) {
    const visibility = { public: "+", private: "−", protected: "#", package: "~", unknown: "?" };
    const name = entity.qualified_name.split(".").at(-1);
    let text = `${visibility[entity.visibility.kind]} ${includeName ? name : ""}`;
    if (entity.signature) {
      const parameters = [];
      let keywordSeparator = false;
      entity.signature.parameters.forEach((parameter, index, all) => {
        if (parameter.kind === "keyword_only" && !keywordSeparator) {
          parameters.push("*");
          keywordSeparator = true;
        }
        if (parameter.kind === "varargs") keywordSeparator = true;
        const prefix = parameter.kind === "varargs" ? "*" : parameter.kind === "kwargs" ? "**" : "";
        parameters.push(prefix + parameter.name + (parameter.annotation ? `: ${parameter.annotation}` : "")
          + (parameter.default_known && parameter.default !== null ? ` = ${parameter.default}` : ""));
        if (parameter.kind === "positional_only" && all[index + 1]?.kind !== "positional_only") parameters.push("/");
      });
      text += `(${parameters.join(", ")}): ${entity.signature.returns || "?"}`;
    } else if (entity.annotation) text += `: ${entity.annotation}`;
    if (entity.initializer !== null && entity.initializer !== undefined) text += ` = ${entity.initializer}`;
    return text;
  }

  function compactUmlText(text, font = `11px ${monoFontFamily}`) {
    const lines = wrapText(text, CARD.w - 32, font);
    if (lines.length <= 2) return text;
    let prefix = lines.slice(0, 2).join(" ").trimEnd();
    while (wrapText(prefix + "…", CARD.w - 32, font).length > 2) prefix = prefix.slice(0, -1);
    return prefix + "…";
  }

  function architectureAssessments(context, id) {
    if (!context.comparison) return [];
    const subjects = new Set([id]);
    for (const entity of context.graph.entities) {
      let parent = architectureParent(entity, context.graph);
      while (parent) {
        if (parent === id) { subjects.add(entity.id); break; }
        const owner = context.graph.entities.find((item) => item.id === parent);
        parent = owner ? architectureParent(owner, context.graph) : null;
      }
    }
    context.graph.relationships.forEach((edge) => {
      if (subjects.has(edge.source_id)) subjects.add(edge.id);
    });
    return context.comparison.assessments.filter((item) => context.graph.origin === "observed"
      ? item.observed_ids.some((id) => subjects.has(id)) : subjects.has(item.subject_id));
  }

  function projectArchitectureScene(context) {
    const { graph, scope } = context;
    const displayEntities = architectureEntities(graph);
    const byId = new Map(displayEntities.map((entity) => [entity.id, entity]));
    const local = displayEntities.filter((entity) => architectureParent(entity, graph) === scope
      && entity.presence !== "referenced");
    const visible = new Map(local.map((entity) => [entity.id, entity]));
    const localIds = new Set(visible.keys());
    const operationScope = ["method", "function"].includes(byId.get(scope)?.kind);
    const coarse = scope === null || byId.get(scope)?.kind === "component";
    const representative = (id) => {
      if (operationScope) return id;
      let current = id;
      let classifier = null;
      let module = null;
      let component = null;
      while (byId.has(current)) {
        if (localIds.has(current)) return current;
        if (current === scope) return current === id && byId.get(current).kind !== "component" ? current : null;
        const entity = byId.get(current);
        if (!classifier && ["class", "interface", "enum"].includes(entity.kind)) classifier = current;
        if (!module && entity.kind === "module") module = current;
        if (coarse && !component && entity.kind === "component") component = current;
        current = architectureParent(entity, graph);
      }
      return component || classifier || module || id;
    };
    const observed = viewMode === "diff" && graph.origin === "declared" ? DATA.observed : null;
    const observedById = new Map((observed ? architectureEntities(observed) : []).map((entity) => [entity.id, entity]));
    const counterparts = new Map();
    for (const match of context.comparison?.correspondences || []) {
      if (match.observed_ids.length !== 1 || !byId.has(match.target_id)) continue;
      const id = match.observed_ids[0];
      if (!counterparts.has(id)) counterparts.set(id, new Set());
      counterparts.get(id).add(match.target_id);
    }
    const targetEntry = (id) => ({ id, entity: byId.get(id), sourceGraph: graph,
      local: localIds.has(id) || id === scope });
    const observedEntry = (id, local = false) => ({ id: `observed:${id}`,
      entity: observedById.get(id), sourceGraph: observed, local });
    const observedRepresentative = (id) => {
      let current = id, child = id, classifier = null, module = null;
      while (observedById.has(current)) {
        if (current === scope) return observedEntry(classifier || child, true);
        if (byId.get(current)?.kind === "component") return targetEntry(representative(current));
        const mapped = [...new Set([...(counterparts.get(current) || [])]
          .map(representative).filter(Boolean))];
        const local = mapped.filter((id) => localIds.has(id));
        const choices = local.length ? local : mapped;
        if (choices.length === 1) {
          if (operationScope && current !== id) {
            return observedEntry(id, choices[0] === scope || localIds.has(choices[0]));
          }
          if (choices[0] === scope && current !== id) return observedEntry(classifier || child, true);
          return targetEntry(choices[0]);
        }
        if (observedLocalIds.has(current)) return observedEntry(current, true);
        const entity = observedById.get(current);
        if (!classifier && ["class", "interface", "enum"].includes(entity.kind)) classifier = current;
        if (!module && entity.kind === "module") module = current;
        child = current;
        current = architectureParent(entity, observed);
      }
      return observedEntry(operationScope ? id : classifier || module || id, scope === null);
    };
    const entries = new Map([...visible].map(([id]) => [id, targetEntry(id)]));
    const observedLocalIds = new Set((observed ? architectureEntities(observed) : []).filter((entity) =>
      ["package", "module"].includes(entity.kind) && entity.presence !== "referenced"
      && architectureParent(entity, observed) === scope).map((entity) => entity.id));
    for (const id of observedLocalIds) {
      if (context.comparison && scope !== null) continue;
      const entry = observedRepresentative(id);
      if (entry.entity && entry.local) entries.set(entry.id, entry);
    }
    const groups = new Map();
    const addSite = (site, source, target, sourceGraph, assessment = null) => {
      if (!source?.entity || !target?.entity || (!source.local && !target.local)) return;
      if (source.id === target.id && site.source_id !== site.target_id) return;
      for (const entry of [source, target]) if (!entries.has(entry.id)) entries.set(entry.id, entry);
      const id = site.kind === "requires" ? site.id
        : `${sourceGraph !== graph ? "observed:" : ""}${site.kind}:${source.id}>${target.id}:${site.resolution}`;
      if (!groups.has(id)) groups.set(id, { id, source: source.id, target: target.id, kind: "dependency",
        relationshipKind: site.kind, sites: [], sourceGraph, assessments: [], resolution: site.resolution,
        state: assessment?.status === "FAIL" ? "violation" : assessment?.status === "UNKNOWN" ? "undecided"
          : sourceGraph.origin === "declared" ? "declared"
          : site.resolution === "partial" ? "undecided" : "observed" });
      const edge = groups.get(id);
      if (!edge.sites.some((item) => item.id === site.id)) edge.sites.push(site);
      if (assessment && !edge.assessments.some((item) => item.id === assessment.id)) edge.assessments.push(assessment);
    };
    for (const site of graph.relationships) {
      if (site.kind === "owns") continue;
      // Component dependencies use imports; operation sites remain in Details and module drill-down.
      if (coarse && !["imports", "requires"].includes(site.kind)) continue;
      if (coarse
          && byId.get(site.source_id)?.presence === "referenced") continue;
      const source = representative(site.source_id);
      const targets = site.target_id ? [site.target_id] : site.candidate_ids;
      for (const endpoint of targets) {
        if (coarse
            && byId.get(endpoint)?.presence === "referenced") continue;
        const target = representative(endpoint);
        addSite(site, targetEntry(source), targetEntry(target), graph);
      }
    }
    const unexpected = (context.comparison?.assessments || []).filter((item) => item.change === "unexpected");
    const observedSites = new Map((observed?.relationships || []).map((site) => [site.id, site]));
    const representedSites = new Set((context.comparison?.assessments || [])
      .filter((match) => graph.relationships.some((site) => site.id === match.subject_id))
      .flatMap((match) => match.observed_ids));
    for (const site of observedSites.values()) {
      const assessment = unexpected.find((item) => item.observed_ids.includes(site.id));
      if (representedSites.has(site.id) || (!assessment && site.kind !== "imports")) continue;
      if (coarse && site.kind !== "imports") continue;
      for (const endpoint of new Set(site.target_id ? [site.target_id] : site.candidate_ids)) {
        addSite(site, observedRepresentative(site.source_id), observedRepresentative(endpoint), observed, assessment);
      }
    }
    for (const assessment of unexpected) for (const id of assessment.observed_ids) {
      const entity = observedById.get(id);
      if (entity && assessment.subject_id === scope) entries.set(`observed:${id}`, observedEntry(id, true));
    }
    const nodes = [...entries.values()].map(({ id, entity, sourceGraph, local }) => {
      const children = architectureEntities(sourceGraph).filter((child) => architectureParent(child, sourceGraph) === entity.id);
      const boundary = (sourceGraph.origin === "observed" ? DATA.target?.component_intents || [] : sourceGraph.component_intents)
        .find((item) => item.component_id === entity.id);
      const assessments = sourceGraph === graph ? architectureAssessments(context, entity.id)
        : unexpected.filter((item) => item.observed_ids.includes(entity.id));
      for (const edge of groups.values()) if (edge.source === id) {
        for (const item of edge.assessments) if (!assessments.some((found) => found.id === item.id)) assessments.push(item);
      }
      const fields = children.filter((child) => child.kind === "attribute");
      const methods = children.filter((child) => child.kind === "method");
      const sections = [
        ["Attributes", fields], ["Operations", methods],
      ].filter(([, entries]) => entries.length).map(([label, entries]) => ({ label,
        lines: [...entries.slice(0, 3).map((entry) => umlMember(entry)),
          ...(entries.length > 3 ? [`… ${entries.length - 3} more · Open selected`] : [])] }));
      return { id, kind: entity.kind, entity, sourceGraph, assessments,
        label: architectureLabel(entity, sourceGraph),
        meta: ["method", "function", "attribute", "binding"].includes(entity.kind)
          ? umlMember(entity, !["method", "function"].includes(entity.kind))
          : sourceGraph !== graph ? `Observed · ${unexpected.some((item) => item.observed_ids.includes(entity.id)) ? "unlisted definition" : entity.kind === "package" ? "namespace" : "relationship endpoint"}`
          : entity.presence === "referenced" ? "Referenced symbol"
            : `${boundary && sourceGraph.origin === "observed" ? "Declared boundary · " : boundary ? `${boundary.role} · ` : ""}${children.length} inner element${children.length === 1 ? "" : "s"}`,
        sections, memberCounts: { fields: fields.length, methods: methods.length }, outside: !local,
        tooltip: `${entity.kind}: ${entity.qualified_name}. ${entity.presence}. ${entity.responsibilities.join(" ")}` };
    });
    const edges = [...groups.values()].map((edge) => {
      const assessments = [...new Map([...edge.assessments, ...(context.comparison?.assessments.filter((item) =>
        edge.sites.some((site) => edge.sourceGraph.origin === "observed"
          ? item.observed_ids.includes(site.id) : site.id === item.subject_id)) || [])]
        .map((item) => [item.id, item])).values()];
      const observedSites = [...new Set((context.comparison?.assessments || [])
        .filter((match) => edge.sites.some((site) => site.id === match.subject_id))
        .flatMap((match) => match.observed_ids))].map((id) => DATA.observed?.relationships.find((site) => site.id === id)).filter(Boolean);
      const findings = (DATA.findings || []).filter((item) => [...edge.sites, ...observedSites]
        .some((site) => item.graph_subject_ids.includes(site.id)));
      const statuses = [...new Set([...assessments, ...findings].map((item) => item.status))];
      const decisionGaps = (DATA.decision_gaps || []).filter((gap) => edge.sourceGraph.origin === "observed"
        && edge.sites.some((site) => gap.relationship_ids.includes(site.id)));
      return { ...edge, observedSites, assessments, findings, decisionGaps,
        state: statuses.includes("FAIL") ? "violation" : statuses.includes("UNKNOWN") || decisionGaps.length ? "undecided" : edge.state,
        tooltip: `${edge.relationshipKind === "requires" ? "Allowed component import" : edge.relationshipKind}${edge.resolution === "partial" ? " candidate; not confirmed" : ""}: ${
          edge.sourceGraph.entities.find((item) => item.id === edge.sites[0].source_id).qualified_name} → ${
          edge.sourceGraph.entities.find((item) => item.id === (edge.sites[0].target_id || edge.sites[0].candidate_ids[0])).qualified_name}; ${
          edge.sites.length + observedSites.length} source or declaration site${edge.sites.length + observedSites.length === 1 ? "" : "s"}.${statuses.length ? ` Core ${statuses.join("/")}${assessments.some((item) => item.change === "unexpected") ? " · unlisted observed relationship" : ""}.` : ""}`,
      };
    });
    if (graph.origin === "declared") {
      for (const inventory of graph.module_inventories.filter((item) => item.component_id === scope)) {
        for (const file of inventory.modules) {
          if (nodes.some((node) => node.entity?.file_path === file.path)) continue;
          nodes.push({ id: `${inventory.id}:file:${encodeURIComponent(file.path)}`,
            kind: "file", label: file.path.split("/").at(-1),
            meta: DATA.observed ? DATA.observed.entities.some((entity) => entity.kind === "module" && entity.presence === "defined" && entity.file_path === file.path) ? "Declared file intent · observed" : "Declared file intent · not observed" : "Declared file intent · Source unavailable",
            tooltip: `${file.path}. ${file.responsibility}`, fileIntent: file, inventory,
            entity: null, sourceGraph: graph, assessments: [],
            findings: (DATA.findings || []).filter((finding) => finding.subjects.includes(file.path)), sections: [],
            memberCounts: { fields: 0, methods: 0 }, outside: false });
        }
      }
    }
    return { nodes, frames: [], edges, owner: scope };
  }

  function selectArchitectureSubject(type, id) {
    umlSelection = { type, id };
    setTargetDetails(true);
    nodeLayer.querySelectorAll("[data-uml-id]").forEach((node) => {
      const selected = type === "node" && node.dataset.umlId === id;
      node.classList.toggle("selected", selected);
      node.setAttribute("aria-pressed", String(selected));
    });
    edgeLayer.querySelectorAll(".hit").forEach((hit) => hit.setAttribute("aria-pressed",
      String(type === "edge" && hit.parentElement.dataset.umlId === id)));
    emphasizeUmlScene(umlSelection);
    architectureInspector(architectureGraphContext(), renderedScene);
    updateOpenSelected();
    if (type === "node") {
      const node = nodeLayer.querySelector(`[data-uml-id="${CSS.escape(id)}"]`);
      if (!node) return;
      const box = node.getBoundingClientRect();
      const bounds = canvas.getBoundingClientRect();
      const left = bounds.left + canvas.clientLeft + 8;
      const top = bounds.top + canvas.clientTop + 8;
      const width = canvas.clientWidth - 16;
      const height = canvas.clientHeight - 16;
      // Opening Details reduces the canvas; keep the selected card in view without relayout.
      canvas.scrollLeft += box.width > width || box.left < left
        ? box.left - left : Math.max(0, box.right - left - width);
      canvas.scrollTop += box.height > height || box.top < top
        ? box.top - top : Math.max(0, box.bottom - top - height);
    }
  }

  function openArchitectureEntity(id, sourceGraph = null) {
    const context = architectureGraphContext();
    const node = sourceGraph ? { entity: architectureEntity(id, sourceGraph), sourceGraph }
      : renderedScene?.nodes.find((item) => item.id === id);
    if (!context || !node?.entity) { selectArchitectureSubject("node", id); return; }
    if (node.sourceGraph === context.graph && node.entity.id === context.scope
        || !architectureHasInterior(node.entity, node.sourceGraph)) {
      selectArchitectureSubject("node", id);
      return;
    }
    const card = renderedScene.nodes.find((item) => item.entity?.id === node.entity.id && item.sourceGraph === node.sourceGraph);
    if (card) umlSelection = { type: "node", id: card.id };
    rememberNavigationState();
    umlPath.push({ id: node.entity.id, origin: node.sourceGraph.origin });
    umlSelection = null;
    focusLabel = null;
    relationshipKind = null;
    elementKind = null;
    positions = {};
    render();
    focusCurrentLevel();
  }

  function leaveArchitectureGraph() {
    if (!umlPath.length) return;
    if (!restoreNavigationState()) {
      umlPath.pop();
      umlSelection = null;
      positions = {};
      render();
    }
    focusCurrentLevel();
  }

  function architectureNavigation(context) {
    const path = [...(context.base ? [{ id: context.base, origin: context.graph.origin }] : []), ...umlPath];
    const entries = [{ label: viewMode === "target" ? "Target architecture" : viewMode === "diff" ? "Architecture diff" : "As-Is architecture", depth: -1 },
      ...path.map((entry, depth) => {
        const graph = entry.origin === "observed" ? DATA.observed : DATA.target;
        return { label: (viewMode === "diff" && entry.origin === "observed" ? "Observed: " : "")
          + architectureLabel(architectureEntity(entry.id, graph), graph), depth };
      })];
    breadcrumb.hidden = false;
    breadcrumb.textContent = "";
    entries.forEach((entry, index) => {
      if (index) breadcrumb.append(" / ");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = entry.label;
      button.disabled = index === entries.length - 1;
      button.addEventListener("click", () => {
        navigationHistory.delete(viewMode);
        if (context.base && entry.depth < 0) {
          umlPath = [];
          umlSelection = null;
          render();
          return;
        }
        umlPath = umlPath.slice(0, entry.depth + (context.base ? 0 : 1));
        umlSelection = null;
        focusLabel = null;
        relationshipKind = null;
        elementKind = null;
        positions = {};
        render();
      });
      breadcrumb.appendChild(button);
    });
    backButton.hidden = !context.base && !umlPath.length;
    backButton.textContent = "Back to " + entries.at(-2)?.label;
  }

  function architectureInspector(context, scene) {
    const { graph } = context;
    const node = umlSelection?.type === "node"
      ? scene.nodes.find((item) => item.id === umlSelection.id) : null;
    if (node?.fileIntent) {
      const observedFile = (DATA.observed?.entities || []).find((entity) => entity.kind === "module"
        && entity.presence === "defined" && entity.file_path === node.fileIntent.path);
      inspectorContent.innerHTML = `<div class="kicker">Independent Target · file intent</div>
        <h2>${esc(node.fileIntent.path)}</h2><p>${esc(node.fileIntent.responsibility)}</p>
        <p>This file inventory does not define classes, methods, imports or calls.</p>
        <p>${DATA.observed ? observedFile ? `Observed module: ${esc(observedFile.qualified_name)}` : "Not in the observed file inventory." : "Source facts are unavailable."} This is separate from a Core verdict.</p>
        <h3>Provenance</h3><p>${node.inventory.provenance.map(esc).join(" · ")}</p>
        <h3>Recorded Core findings</h3>${findingMarkup(node.findings || [])}`;
      return;
    }
    const entity = node?.entity || (!umlSelection
      ? architectureEntity(context.scope, graph) : null) || null;
    const edge = umlSelection?.type === "edge"
      ? scene.edges.find((item) => item.id === umlSelection.id) : null;
    const entityGraph = node?.sourceGraph || edge?.sourceGraph || graph;
    const related = new Set([entity?.id || context.scope]);
    architectureEntities(entityGraph).forEach((item) => {
      let parent = architectureParent(item, entityGraph);
      while (parent) {
        if (related.has(parent)) { related.add(item.id); break; }
        const owner = architectureEntity(parent, entityGraph);
        parent = owner ? architectureParent(owner, entityGraph) : null;
      }
    });
    const siteEntries = (edge?.sites || entityGraph.relationships.filter((item) =>
      related.has(item.source_id) || entity && (related.has(item.target_id)
        || item.candidate_ids.some((id) => related.has(id)))))
      .map((site) => ({ site, sourceGraph: entityGraph }));
    for (const site of edge?.observedSites || []) siteEntries.push({ site, sourceGraph: DATA.observed });
    if (node) for (const connection of scene.edges) {
      if (connection.sourceGraph === entityGraph || ![connection.source, connection.target].includes(node.id)) continue;
      for (const site of connection.sites) if (!siteEntries.some((entry) => entry.site.id === site.id
          && entry.sourceGraph === connection.sourceGraph)) siteEntries.push({ site, sourceGraph: connection.sourceGraph });
    }
    const sites = siteEntries.map((entry) => entry.site);
    const assessments = edge?.assessments || node?.assessments || architectureAssessments(context, context.scope);
    const problems = assessments.filter((item) => item.status !== "PASS");
    const matches = assessments.filter((item) => item.status === "PASS");
    const assessmentDetails = (items) => items.map((item) => {
      const wanted = (context.comparison ? DATA.target : graph).entities.find((entry) => entry.id === item.subject_id);
      const actual = (DATA.observed?.entities || []).filter((entry) => item.observed_ids.includes(entry.id));
      return `<li><strong>${esc(item.status)}</strong> · ${esc(item.aspect)} · ${esc(item.change)}<p>${esc(item.reason)}</p>${wanted?.signature && item.aspect === "signature" ? `<p>Target: <code>${esc(umlMember(wanted))}</code></p>${actual.map((entry) => `<p>As-Is: <code>${esc(umlMember(entry))}</code></p>`).join("")}` : ""}</li>`;
    }).join("");
    const evidenceGraphs = new Set([graph, entityGraph, ...siteEntries.map((entry) => entry.sourceGraph),
      ...(context.comparison && DATA.observed ? [DATA.observed] : [])]);
    const evidence = new Map([...evidenceGraphs].flatMap((item) => item.evidence)
      .map((item) => [item.id, item]));
    const proofIds = [...new Set([...(entity?.evidence_ids || []), ...sites.flatMap((item) => item.evidence_ids),
      ...(entity?.definition_contexts || []).flatMap((item) => item.evidence_ids),
      ...assessments.flatMap((item) => item.evidence_ids)])];
    const proof = proofIds.map((id) => evidence.get(id)).filter(Boolean);
    const decisionGaps = (DATA.decision_gaps || []).filter((gap) => sites.some((site) => gap.relationship_ids.includes(site.id)));
    const scope = entity?.id || context.scope;
    const coverage = entityGraph.coverage.filter((item) => item.scope_id === scope);
    const children = entityGraph.entities.filter((item) => architectureParent(item, entityGraph) === entity?.id);
    const boundary = !edge && (entityGraph.origin === "observed" ? DATA.target?.component_intents || [] : entityGraph.component_intents)
      .find((item) => item.component_id === scope);
    const entries = (items) => items === null ? "Not declared" : items.length ? items.map(esc).join("<br>") : "Explicitly empty";
    const physicalScope = !edge && graph.origin === "declared" && (!entity || entity.kind === "component");
    const inventories = physicalScope ? graph.module_inventories.filter((item) => item.component_id === scope) : [];
    const assignedLayouts = new Set(graph.component_intents.flatMap((item) => item.layout_rule_ids));
    const layouts = physicalScope ? graph.layout_rules.filter((rule) => scope === null
      ? !assignedLayouts.has(rule.id) : boundary?.layout_rule_ids.includes(rule.id)) : [];
    const plannedFiles = inventories.flatMap((item) => item.modules);
    const globalApi = !edge && graph.origin === "declared" && scope === null ? graph.public_api : [];
    const permissionGraph = DATA.target;
    const externalScopes = (permissionGraph?.external_scopes || []).filter((rule) => scope === null
      || entity?.qualified_name === rule.dependency || siteEntries.some(({site, sourceGraph}) => {
        const target = architectureEntity(site.target_id, sourceGraph)?.qualified_name || site.expression || "";
        return target === rule.dependency || target.startsWith(`${rule.dependency}.`);
      }));

    inspectorContent.innerHTML = `<div class="kicker">${context.comparison ? "Core comparison" : entityGraph.origin === "observed" ? entity?.kind === "component" ? "Declared navigation boundary · observed source" : "Observed" : "Independent Target"} UML</div>
      <h2>${esc(entity?.qualified_name || (edge?.relationshipKind === "requires" ? "Allowed component import" : edge?.relationshipKind) || "Architecture scope")}</h2>
      ${edge?.routingWarning ? `<p role="status">${esc(ROUTING_WARNING)}</p>` : ""}
      ${entity ? `<dl class="kv"><dt>Kind</dt><dd>${esc(entity.kind)}</dd>${entity.kind !== "component" ? `<dt>Language visibility</dt><dd>${esc(entity.visibility.kind)} · ${esc(entity.visibility.basis)}</dd>` : ""}${entity.signature || entity.annotation ? `<dt>Signature or annotation</dt><dd><code>${esc(umlMember(entity))}</code></dd>` : ""}</dl>
      ${entity.responsibilities.map((text) => `<p>${esc(text)}</p>`).join("")}${entityGraph.origin === "declared" && !entity.responsibilities.length ? "<p>No declared responsibility.</p>" : ""}` : ""}
      ${entity?.definition_contexts?.length ? `<h3>Definition context</h3><p>Recorded under control flow. Runtime name binding is not proven.</p><ol>${entity.definition_contexts.map((item) => `<li><code>${esc(item.kind)} · ${esc(item.branch)}</code></li>`).join("")}</ol>` : ""}
      ${entity?.initializer != null ? `<h3>Static assignment site</h3><p><code>${esc(umlMember(entity))}</code></p><p>Source value assigned at this site. This does not identify a live object or its current value.</p>` : ""}
      ${decisionGaps.length ? `<h3>Open dependency decisions</h3><p>These observed component imports have no declared dependency decision. This is not a Core UNKNOWN verdict.</p><ul>${decisionGaps.map((gap) => `<li>${esc(architectureLabel(architectureEntity(gap.source_id, DATA.target), DATA.target))} → ${esc(architectureLabel(architectureEntity(gap.target_id, DATA.target), DATA.target))}</li>`).join("")}</ul>` : ""}
      ${externalScopes.length ? `<h3>External dependency permissions</h3><ul>${externalScopes.map((rule) => `<li><strong>${esc(rule.dependency)}</strong> · <code>${esc(rule.id)}</code><p>Allowed prefixes: ${entries(rule.allowed_sources)}<br>Exact modules: ${entries(rule.exact_sources)}</p><p>${esc(rule.rationale)}</p><p>Decided by ${esc(rule.decided_by)} · ${rule.provenance.map(esc).join(" · ")}</p></li>`).join("")}</ul>` : ""}
      ${boundary ? `<h3>Component intent</h3><dl class="kv">
        <dt>Component role</dt><dd>${esc(boundary.role)}</dd>
        <dt>Package ownership</dt><dd>${entries(boundary.packages)}</dd>
        <dt>Exact module ownership</dt><dd>${entries(boundary.exact_modules)}</dd>
        <dt>Target namespace</dt><dd>${esc(boundary.namespace || "Not declared")}</dd>
        <dt>Published API</dt><dd>${entries(boundary.public)}</dd>
        <dt>Planned interface (proposed)</dt><dd>${entries(boundary.planned)}</dd>
        ${boundary.decided_by ? `<dt>Decided by</dt><dd>${esc(boundary.decided_by)}</dd>` : ""}
        ${boundary.inside ? `<dt>Inner contract</dt><dd>${esc(boundary.inside)}</dd>` : ""}
        </dl>${boundary.forbidden_responsibilities.length ? `<h3>Excluded responsibilities</h3><ul class="plain">${boundary.forbidden_responsibilities.map((text) => `<li>${esc(text)}</li>`).join("")}</ul>` : ""}` : ""}
      ${globalApi.length ? `<h3>Global published API</h3><p>API selectors. Symbol details come from explicit UML intent.</p><ul class="plain">${globalApi.map((entry) => `<li><code>${esc(entry.selector)}</code><p>${entry.provenance.map(esc).join(" · ")}</p></li>`).join("")}</ul>` : ""}
      ${physicalScope ? `${plannedFiles.length ? `<details><summary>Module inventory · ${plannedFiles.length} planned ${plannedFiles.length === 1 ? "file" : "files"}</summary>
        <p>File intent does not define classes or calls.</p><ul class="plain">${plannedFiles.map((item) => `<li><code>${esc(item.path)}</code><p>${esc(item.responsibility)}</p></li>`).join("")}</ul>
        <p>${[...new Set(inventories.flatMap((item) => item.provenance))].map(esc).join(" · ")}</p></details>`
        : `<h3>Module inventory</h3><p>${inventories.length ? "Explicitly empty" : "Not declared"}</p>`}
        ${layouts.length ? `<details><summary>Permitted package layout · ${layouts.length} ${layouts.length === 1 ? "rule" : "rules"}</summary>
          <p>Permission does not require existence.</p><ul class="plain">${layouts.map((rule) => `<li><strong>${esc(rule.root)}</strong><p>${esc(rule.rationale)}</p><p>Allowed immediate children: ${rule.allowed_children.length ? rule.allowed_children.map(esc).join(", ") : "Explicitly empty"}</p><p>${esc(rule.decided_by)} · ${rule.provenance.map(esc).join(" · ")}</p></li>`).join("")}</ul></details>`
          : context.scope === null ? "<h3>Permitted package layout</h3><p>Not declared</p>" : ""}` : ""}
      ${children.length ? `<h3>Inner elements</h3><ul class="plain">${children.map((child) =>
        `<li><code>${esc(umlMember(child))}</code>${architectureHasInterior(child, entityGraph) ? ` <button type="button" data-uml-detail="${esc(child.id)}">Open</button>` : ""}</li>`).join("")}</ul>` : ""}
      ${assessments.length ? `<h3>Core assessments</h3>${problems.length ? `<ul class="plain">${assessmentDetails(problems)}</ul>` : ""}${matches.length ? `<details><summary>${matches.length} matched assessments</summary><ul class="plain">${assessmentDetails(matches)}</ul></details>` : ""}`
        : context.comparison && entityGraph.origin === "observed" ? "<h3>Core assessments</h3><p>No Core assessment for this observed scope.</p>" : ""}
      ${sites.length ? `<h3>Relationship sites</h3><ul class="plain">${siteEntries.map(({ site, sourceGraph }) =>
        `<li><code>${esc(site.kind)}</code> · ${esc(site.resolution === "not_applicable" ? "declared" : site.resolution)}<p><code>${esc(sourceGraph.entities.find((item) => item.id === site.source_id)?.qualified_name)} → ${esc(sourceGraph.entities.find((item) => item.id === site.target_id)?.qualified_name || (site.candidate_ids.length ? "candidates" : "unresolved"))}</code></p>${site.kind === "requires" ? `<p>Allowed component import. This does not require an import or call.</p><p>${site.through.length ? `Through: <code>${site.through.map(esc).join(", ")}</code>` : "Published interface not narrowed"}${site.decided_by ? ` · Decided by: ${esc(site.decided_by)}` : ""}</p>` : ""}${site.expression ? `<code>${esc(site.expression)}</code>` : ""}${site.reason ? `<p>${esc(site.reason)}</p>` : ""}</li>`).join("")}</ul>` : ""}
      ${coverage.length ? `<h3>Coverage</h3><ul class="plain">${coverage.map((item) =>
        `<li>${esc([...item.entity_kinds, ...item.relationship_kinds].join(", "))}: ${esc(item.status)}${item.reason ? ` · ${esc(item.reason)}` : ""}</li>`).join("")}</ul>` : ""}
      ${proof.length ? `<h3>Source sites</h3><ul class="plain">${proof.map((item) =>
        `<li><code>${esc(item.file)}:${item.line}:${item.column}</code><pre>${esc(item.excerpt)}</pre></li>`).join("")}</ul>` : ""}
      ${[...(entity?.provenance || []), ...sites.flatMap((item) => item.provenance)].length ? `<h3>Provenance</h3><ul class="plain">${[...new Set([...(entity?.provenance || []), ...sites.flatMap((item) => item.provenance)])].map((item) => `<li>${esc(item)}</li>`).join("")}</ul>` : ""}
      ${!entity && !edge ? "<p>Select a visible element or connection for its recorded details.</p>" : ""}`;
    if (viewMode === "diff" || umlSelection) {
      const ids = new Set(edge ? edge.sites.map((site) => site.id) : related);
      if (!edge) for (const sourceGraph of new Set([entityGraph, DATA.observed].filter(Boolean))) {
        for (const item of architectureEntities(sourceGraph)) {
          let current = item.id;
          while (current) {
            if (ids.has(current)) { ids.add(item.id); break; }
            const owner = architectureEntity(current, sourceGraph);
            current = owner ? architectureParent(owner, sourceGraph) : null;
          }
        }
        for (const site of sourceGraph.relationships) if (ids.has(site.source_id)
            || ids.has(site.target_id) || site.candidate_ids.some((id) => ids.has(id))) ids.add(site.id);
      }
      const known = new Set([DATA.observed, DATA.target].filter(Boolean)
        .flatMap((sourceGraph) => [...sourceGraph.entities, ...sourceGraph.relationships].map((item) => item.id)));
      const globalFindings = (DATA.findings || []).filter((item) => !item.graph_subject_ids.some((id) => known.has(id)));
      const findings = (DATA.findings || []).filter((item) => !globalFindings.includes(item)
        && (edge ? edge.findings.includes(item) : context.scope === null && !umlSelection
          || item.graph_subject_ids.some((id) => ids.has(id))));
      inspectorContent.insertAdjacentHTML("beforeend", `<h3>Recorded Core findings</h3>${findingMarkup(findings)}${globalFindings.length ? `<details><summary>Global or unmapped findings · ${globalFindings.length}</summary>${findingMarkup(globalFindings)}</details>` : ""}`);
    }
    inspectorContent.querySelectorAll("[data-uml-detail]").forEach((button) =>
      button.addEventListener("click", () => openArchitectureEntity(button.dataset.umlDetail, entityGraph)));
  }

  function renderArchitectureGraph(context) {
    const focus = document.activeElement.closest("[data-uml-id]")?.dataset.umlId;
    const legendFocus = document.activeElement.closest(".flow-legend button")?.dataset.relationshipKind;
    root.dataset.view = viewMode;
    flowHeading.textContent = "Architecture explorer";
    viewButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.flowView === viewMode)));
    canvas.hidden = false;
    alternative.hidden = true;
    emptyLayer.textContent = "";
    architectureNavigation(context);
    const complete = projectArchitectureScene(context);
    const kinds = [...new Set(complete.edges.map((edge) => edge.relationshipKind))].sort();
    if (!kinds.includes(relationshipKind)) relationshipKind = null;
    const elementKinds = [...new Set(complete.nodes.map((node) => node.kind))].sort();
    if (!elementKinds.includes(elementKind)) elementKind = null;
    elementKindInput.innerHTML = '<option value="">All kinds</option>' + elementKinds.map((kind) =>
      `<option value="${esc(kind)}">${esc(kind)} · ${complete.nodes.filter((node) => node.kind === kind).length}</option>`).join("");
    elementKindInput.value = elementKind || "";
    const referenceOverview = context.graph.origin === "observed"
      && architectureEntity(context.scope, context.graph)?.kind === "module" && !focusLabel && !relationshipKind && !elementKind;
    const typeContext = new Set(complete.edges.filter((edge) => ["inherits", "realizes"].includes(edge.relationshipKind))
      .flatMap((edge) => [edge.source, edge.target]));
    const elements = complete.nodes.filter((node) => (!elementKind || node.kind === elementKind)
      && (!referenceOverview || node.entity?.presence !== "referenced"
        || typeContext.has(node.id) || ["class", "interface", "enum", "module"].includes(node.kind)));
    const elementIds = new Set(elements.map((node) => node.id));
    if (!elementIds.has(focusLabel)) focusLabel = null;
    focusInput.innerHTML = '<option value="">All elements</option>' + [...complete.nodes.filter((node) => !elementKind || node.kind === elementKind)]
      .sort((left, right) => left.label.localeCompare(right.label) || left.id.localeCompare(right.id)).map((node) =>
      `<option value="${esc(node.id)}">${esc(node.label)} · ${esc(node.kind)}${node.outside ? " · outside" : ""}</option>`).join("");
    focusInput.value = focusLabel || "";
    focusInput.disabled = !elements.length;
    const edges = complete.edges.filter((edge) => (!violationsOnly.checked || edge.state === "violation")
      && (!relationshipKind || edge.relationshipKind === relationshipKind)
      && elementIds.has(edge.source) && elementIds.has(edge.target)
      && (!focusLabel || edge.source === focusLabel || edge.target === focusLabel));
    const neighbors = new Set([focusLabel, ...edges.flatMap((edge) => [edge.source, edge.target])]);
    const scene = { ...complete, edges,
      nodes: elements.filter((node) => focusLabel ? neighbors.has(node.id)
        : !node.outside || edges.some((edge) => edge.source === node.id || edge.target === node.id)) };
    if (umlSelection && !(umlSelection.type === "node" ? scene.nodes : edges)
      .some((item) => item.id === umlSelection.id)) umlSelection = null;
    const classifiers = scene.nodes.some((node) => !node.outside
      && ["class", "interface", "enum"].includes(node.kind));
    const hierarchy = edges.filter((edge) => ["inherits", "realizes"].includes(edge.relationshipKind));
    const hierarchyNodes = new Set(hierarchy.flatMap((edge) => [edge.source, edge.target]));
    // A mostly disconnected type inventory needs a grid, not rows behind one small hierarchy.
    const rankHierarchy = hierarchyNodes.size * 2 >= scene.nodes.length;
    const ranks = computeRanks({ components: scene.nodes.map((node) => ({ label: node.id })) },
      edges.filter((edge) => edge.source !== edge.target && edge.resolution !== "partial"
        && (!classifiers || rankHierarchy && ["inherits", "realizes"].includes(edge.relationshipKind))));
    scene.nodes.forEach((node) => { node.rank = ranks.get(node.id); });
    filterStatus.textContent = focusLabel || relationshipKind || elementKind
      ? `${[focusLabel ? "Direct neighbors" : null, elementKind ? `Elements: ${elementKind}` : null, relationshipKind ? `Relationships: ${relationshipKind}` : null].filter(Boolean).join(" · ")} · ${scene.nodes.length} of ${complete.nodes.length} elements · ${edges.length} of ${complete.edges.length} connections`
      : referenceOverview ? "Definitions and type context; referenced symbols remain in relationship filters, Focus and Details"
        : "All elements and connections at this level";
    memberPreviewsButton.hidden = !scene.nodes.some((node) => node.sections.length);
    if (!memberPreviews) for (const node of scene.nodes) {
      if (node.sections.length) {
        const counts = `${node.memberCounts.fields} fields · ${node.memberCounts.methods} methods`;
        node.meta = node.sourceGraph === context.graph ? counts : `${node.meta} · ${counts}`;
        node.sections = [];
      }
    }
    if (!scene.nodes.length) {
      const text = el("text", { x: "32", y: "32", fill: "var(--ck-muted)" });
      text.textContent = "No elements or resolved connections in this scope. See Details for recorded sites.";
      emptyLayer.appendChild(text);
    }
    measureUmlCards(scene.nodes);
    positions = layoutUmlScene(scene, true).positions;
    const emphasize = (preview = null) => emphasizeUmlScene(preview || umlSelection, Boolean(preview));
    renderUmlScene(scene, {
      frame() {},
      edge(drawn, route) {
        drawn.hit.setAttribute("aria-pressed", String(umlSelection?.type === "edge" && umlSelection.id === route.edge.id));
        drawn.hit.addEventListener("click", (event) => {
          event.stopPropagation();
          selectArchitectureSubject("edge", route.edge.id);
        });
        drawn.hit.addEventListener("keydown", (event) => {
          if (["Enter", " "].includes(event.key)) {
            event.preventDefault();
            selectArchitectureSubject("edge", route.edge.id);
          }
        });
        drawn.group.addEventListener("pointerenter", () => emphasize({ type: "edge", id: route.edge.id }));
        drawn.group.addEventListener("pointerleave", () => emphasize());
        drawn.hit.addEventListener("focus", () => emphasize({ type: "edge", id: route.edge.id }));
        drawn.hit.addEventListener("blur", () => emphasize());
      },
      node(group, node) {
        if (node.outside) group.dataset.outside = "true";
        group.classList.toggle("target-node", node.sourceGraph.origin === "declared");
        group.classList.toggle("selected", umlSelection?.type === "node" && umlSelection.id === node.id);
        group.setAttribute("aria-pressed", String(umlSelection?.type === "node" && umlSelection.id === node.id));
        group.addEventListener("click", (event) => {
          event.stopPropagation();
          skipSvgClick = false;
          if (event.detail === 0) selectArchitectureSubject("node", node.id);
        });
        group.addEventListener("dblclick", (event) => { event.preventDefault(); openArchitectureEntity(node.id); });
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter") { event.preventDefault(); openArchitectureEntity(node.id); }
          if (event.key === " ") { event.preventDefault(); selectArchitectureSubject("node", node.id); }
        });
        group.addEventListener("pointerenter", (event) => {
          if (event.pointerType === "mouse") emphasize({ type: "node", id: node.id });
        });
        group.addEventListener("pointerleave", () => emphasize());
        group.addEventListener("pointerdown", (event) => {
          event.stopPropagation();
          capturePointer(svg, event);
          dragState = { label: node.id, pointerType: event.pointerType, x: event.clientX, y: event.clientY,
            start: { ...positions[node.id] }, moved: 0 };
        });
      },
    });
    emphasize();
    for (const item of [...scene.nodes, ...scene.edges]) {
      const findings = item.entity ? (DATA.findings || []).filter((finding) => finding.graph_subject_ids.includes(item.entity.id)) : item.findings || [];
      const statuses = [...(item.assessments || []), ...findings].map((receipt) => receipt.status);
      const status = statuses.includes("FAIL") ? "FAIL" : statuses.includes("UNKNOWN") ? "UNKNOWN"
        : statuses.includes("PASS") ? "PASS" : null;
      const element = svg.querySelector(`[data-uml-id="${CSS.escape(item.id)}"]`);
      if (status) {
        element.dataset.assessmentStatus = status;
        if (item.entity) {
          const label = el("text", { class: "uml-assessment", x: String(CARD.w - 12),
            y: String(cardHeight(item.id) - 8), "text-anchor": "end" });
          label.textContent = status;
          element.appendChild(label);
        }
      }
    }
    legend.textContent = "";
    for (const kind of [null, ...kinds]) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "flow-legend-item flow-fit";
      item.dataset.relationshipKind = kind || "";
      item.setAttribute("aria-pressed", String(relationshipKind === kind));
      const count = kind ? complete.edges.filter((edge) => edge.relationshipKind === kind).length : complete.edges.length;
      item.textContent = kind
        ? `${kind === "inherits" ? "△" : kind === "realizes" ? "┄△" : "⇢"} ${kind === "requires" ? "Allowed component import" : kind} · ${count}`
        : `All relationships · ${count}`;
      item.title = `Show ${kind || "all"} relationships at this level · ${count} connections`;
      legend.appendChild(item);
    }
    if (complete.edges.some((edge) => edge.assessments.some((item) => item.change === "unexpected"))) {
      const item = document.createElement("span");
      item.className = "flow-legend-item";
      item.textContent = `Core ${[...new Set(complete.edges.filter((edge) => edge.assessments.some((item) => item.change === "unexpected"))
        .flatMap((edge) => edge.assessments.map((item) => item.status)))].join("/")} · unlisted observed relationships`;
      legend.appendChild(item);
    }
    const routeWarnings = scene.edges.filter((edge) => edge.routingWarning).length;
    if (routeWarnings) {
      const warning = document.createElement("span");
      warning.className = "flow-legend-hint";
      warning.setAttribute("role", "status");
      warning.textContent = `${routeWarnings} routing warnings · ${ROUTING_WARNING}`;
      legend.appendChild(warning);
    }
    const unresolved = context.graph.relationships.filter((edge) => edge.target_id === null).length;
    const hint = document.createElement("span");
    hint.className = "flow-legend-hint";
    hint.textContent = `${scene.nodes.length} visible elements · ${scene.edges.length} connections · ${unresolved} uncertain sites in graph`;
    if ((context.scope === null || architectureEntity(scene.owner, context.graph)?.kind === "component") && context.graph.origin === "observed")
      hint.textContent += " · Internal import overview; other source sites remain in Details and module drill-down";
    if (context.comparison) hint.textContent += ` · Core: ${context.comparison.status}`;
    legend.appendChild(hint);
    architectureInspector(context, scene);
    inspector.hidden = !targetDetailsOpen;
    updateOpenSelected();
    sizeDiagram();
    renderGraphTable(context, scene);
    if (focus) svg.querySelector(`[data-uml-id="${CSS.escape(focus)}"]`)?.focus({ preventScroll: true });
    if (legendFocus !== undefined) legend.querySelector(`button[data-relationship-kind="${CSS.escape(legendFocus)}"]`)
      ?.focus({ preventScroll: true });
  }

  function sizeDiagram() {
    const bounds = viewport.getBBox();
    if (!bounds.width || !bounds.height) return;
    if (positions !== sizedPositions) {
      diagramOrigin = null;
      canvas.scrollLeft = 0;
      canvas.scrollTop = 0;
      sizedPositions = positions;
    }
    const padding = 24;
    const nextX = viewMode === "target"
      ? bounds.x - Math.max(padding, (canvas.clientWidth / transform.k - bounds.width) / 2)
      : bounds.x - padding;
    const nextY = bounds.y - padding;
    if (!diagramOrigin) {
      diagramOrigin = { x: nextX, y: nextY };
      scrollRemainderX = 0;
      scrollRemainderY = 0;
    }
    let scrollX = 0;
    let scrollY = 0;
    // Keep the SVG origin fixed during drag; grow left/up with native-scroll compensation.
    if (dragState && nextX < diagramOrigin.x) {
      scrollX = (diagramOrigin.x - nextX) * transform.k;
      diagramOrigin.x = nextX;
    }
    if (dragState && nextY < diagramOrigin.y) {
      scrollY = (diagramOrigin.y - nextY) * transform.k;
      diagramOrigin.y = nextY;
    }
    const viewWidth = Math.max(
      bounds.x + bounds.width + padding - diagramOrigin.x,
      (canvas.clientWidth + canvas.scrollLeft + scrollX) / transform.k,
    );
    const viewHeight = Math.max(
      bounds.y + bounds.height + padding - diagramOrigin.y,
      (canvas.clientHeight + canvas.scrollTop + scrollY) / transform.k,
    );
    svg.setAttribute("viewBox", `${diagramOrigin.x} ${diagramOrigin.y} ${viewWidth} ${viewHeight}`);
    const style = getComputedStyle(svg);
    const horizontalBorder = parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth);
    const verticalBorder = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    svg.style.width = `${viewWidth * transform.k + horizontalBorder}px`;
    svg.style.height = `${viewHeight * transform.k + verticalBorder}px`;
    // Native scroll rounding must not accumulate across pointer moves.
    if (scrollX) {
      const nextScroll = canvas.scrollLeft + scrollX + scrollRemainderX;
      canvas.scrollLeft = nextScroll;
      scrollRemainderX = nextScroll - canvas.scrollLeft;
    }
    if (scrollY) {
      const nextScroll = canvas.scrollTop + scrollY + scrollRemainderY;
      canvas.scrollTop = nextScroll;
      scrollRemainderY = nextScroll - canvas.scrollTop;
    }
    zoomValue.textContent = `${Math.round(transform.k * 100)}%`;
  }

  function fit() {
    const bounds = viewport.getBBox();
    if (!bounds.width || !bounds.height || !canvas.clientWidth || !canvas.clientHeight) return;
    // Focused neighborhoods stay readable; oversized content uses native scrolling.
    transform.k = Math.max(focusLabel || umlSelection?.type === "node" ? 1 : 0, Math.min(
      1.4,
      canvas.clientWidth / (bounds.width + 48),
      canvas.clientHeight / (bounds.height + 48),
    ));
    diagramOrigin = null;
    sizeDiagram();
    canvas.scrollLeft = 0;
    canvas.scrollTop = 0;
    const selectedPosition = architectureGraphContext() && umlSelection?.type === "node"
      ? positions[umlSelection.id] : null;
    if (selectedPosition) {
      canvas.scrollLeft = (selectedPosition.x - diagramOrigin.x + CARD.w / 2) * transform.k
        - canvas.clientWidth / 2;
      canvas.scrollTop = (selectedPosition.y - diagramOrigin.y + cardHeight(umlSelection.id) / 2) * transform.k
        - canvas.clientHeight / 2;
    }
  }

  function zoomBy(factor) {
    transform.k = Math.min(2.4, Math.max(0.1, transform.k * factor));
    sizeDiagram();
  }

  function architectureGraphContext() {
    const entry = umlPath.at(-1);
    const declared = ["target", "diff"].includes(viewMode);
    const graph = entry?.origin === "observed" || !declared ? DATA.observed : DATA.target;
    return graph ? { graph, base: null, scope: entry?.id || null,
      comparison: viewMode === "diff" ? DATA.comparison : null } : null;
  }

  function currentState() {
    return { umlPath: [...umlPath], umlSelection, focusLabel, relationshipKind, elementKind,
      positions: Object.fromEntries(Object.entries(positions).map(([id, point]) => [id, { ...point }])),
      zoom: transform.k, details: targetDetailsOpen, scopeNotice };
  }

  function restoreState(state) {
    ({ umlPath, umlSelection, focusLabel, relationshipKind, elementKind, positions, scopeNotice } = state);
    transform.k = state.zoom;
    setTargetDetails(state.details);
  }

  function rememberNavigationState() {
    if (!navigationHistory.has(viewMode)) navigationHistory.set(viewMode, []);
    navigationHistory.get(viewMode).push(currentState());
  }

  function restoreNavigationState() {
    const previous = navigationHistory.get(viewMode)?.pop();
    if (!previous) return false;
    restoreState(previous);
    render();
    return true;
  }

  function focusCurrentLevel() {
    const subject = umlSelection && svg.querySelector(`[data-uml-id="${CSS.escape(umlSelection.id)}"]`);
    (subject?.querySelector(".hit") || subject || nodeLayer.querySelector(".node") || flowHeading)
      .focus({ preventScroll: true });
  }

  function updateOpenSelected() {
    const node = umlSelection?.type === "node" && renderedScene?.nodes.find((item) => item.id === umlSelection.id);
    openSelectedButton.disabled = !node?.entity || !architectureHasInterior(node.entity, node.sourceGraph);
    openSelectedButton.textContent = node ? `Open selected ${node.label}` : "Open selected";
  }

  function findingMarkup(findings) {
    return findings.length ? `<ul class="plain">${findings.map((item) => `<li class="${item.status === "FAIL" ? "violation-card" : "unknown-card"}"><strong>${esc(item.status)} · ${esc(item.title)}</strong><p><code>${item.rule_ids.map(esc).join(", ")}</code></p><p>${item.subjects.map(esc).join(", ")}</p></li>`).join("")}</ul>` : "<p>No recorded failures or UNKNOWN findings. This is not a completeness claim.</p>";
  }

  function scopeCounterpart(entry, graph) {
    if (!graph) return { entity: null, ambiguous: false };
    const source = entry.origin === "observed" ? DATA.observed : DATA.target;
    const original = architectureEntity(entry.id, source);
    if (source === graph || original?.kind === "component") {
      return { entity: architectureEntity(entry.id, graph), ambiguous: false };
    }
    const matches = (DATA.comparison?.correspondences || []).filter((match) =>
      graph.origin === "declared" ? match.observed_ids.includes(entry.id) : match.target_id === entry.id);
    const ids = [...new Set(matches.flatMap((match) =>
      graph.origin === "declared" ? [match.target_id] : match.observed_ids))];
    const ambiguous = ids.length > 1 || matches.some((match) => match.observed_ids.length > 1);
    return { entity: !ambiguous && ids.length === 1 ? architectureEntity(ids[0], graph) : null, ambiguous };
  }

  function architecturePath(entity, graph) {
    const path = [];
    while (entity) {
      path.unshift({ id: entity.id, origin: graph.origin });
      entity = architectureEntity(architectureParent(entity, graph), graph);
    }
    return path;
  }

  function switchArchitectureView(nextView) {
    if (nextView === viewMode) return;
    viewStates.set(viewMode, currentState());
    const entry = umlPath.at(-1);
    let graph = ["target", "diff"].includes(nextView) ? DATA.target : DATA.observed;
    // Diff can retain a recorded observed interior without assigning it a Target identity.
    if (nextView === "diff" && entry?.origin === "observed"
        && !scopeCounterpart(entry, graph).entity) graph = DATA.observed;
    const counterpart = entry ? scopeCounterpart(entry, graph) : null;
    viewMode = nextView;
    scopeNotice = null;
    let path = counterpart?.entity ? architecturePath(counterpart.entity, graph) : [];
    if (entry && !counterpart.entity) {
      for (const ancestor of [...umlPath].reverse().slice(1)) {
        const nearest = scopeCounterpart(ancestor, graph).entity;
        if (nearest) { path = architecturePath(nearest, graph); break; }
      }
      const source = entry.origin === "observed" ? DATA.observed : DATA.target;
      scopeNotice = { label: architectureEntity(entry.id, source).qualified_name,
        ambiguous: counterpart.ambiguous, nearestPath: path };
    }
    const saved = viewStates.get(viewMode);
    const restore = !scopeNotice && saved && !saved.scopeNotice
      && JSON.stringify(saved.umlPath.at(-1) || null) === JSON.stringify(path.at(-1) || null);
    if (restore) restoreState(saved);
    else {
      if (!scopeNotice) umlPath = path;
      umlSelection = null; focusLabel = null; relationshipKind = null; elementKind = null;
      positions = {}; transform.k = 1;
      navigationHistory.delete(viewMode);
    }
    render();
    if (!restore && !scopeNotice) fit();
  }

  function renderGraphTable(context, scene) {
    const tableView = ["actual", "structure", "review"].includes(viewMode);
    canvas.hidden = tableView;
    alternative.hidden = !tableView;
    if (!tableView) return;
    const rows = viewMode === "actual" ? context.graph.entities.filter((item) => item.kind === "module" && item.presence === "defined")
      : scene.nodes.map((node) => node.entity).filter(Boolean);
    alternative.innerHTML = viewMode === "review" ? `<h2>Recorded Core findings</h2>${findingMarkup(DATA.findings || [])}`
      : `<h2>${viewMode === "actual" ? "Observed modules" : "Architecture structure"}</h2><table><thead><tr><th>Kind</th><th>Name</th><th>Visibility</th><th>Source</th></tr></thead><tbody>${rows.map((entity) => `<tr><td>${esc(entity.kind)}</td><td><button type="button" data-uml-table="${esc(entity.id)}">${esc(entity.qualified_name)}</button></td><td>${esc(entity.visibility.kind)}</td><td>${esc(entity.file_path || "")}</td></tr>`).join("")}</tbody></table>`;
    alternative.querySelectorAll("[data-uml-table]").forEach((button) => button.addEventListener("click", () => {
      openArchitectureEntity(button.dataset.umlTable, context.graph);
      viewMode = "diagram";
      render();
      fit();
    }));
  }

  function render() {
    const context = architectureGraphContext();
    root.dataset.umlGraph = "true";
    root.dataset.view = viewMode;
    elementKindControl.hidden = !context;
    if (scopeNotice) {
      viewButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.flowView === viewMode)));
      architectureNavigation({ base: null });
      breadcrumb.querySelectorAll("button").forEach((button) => { button.disabled = true; });
      canvas.hidden = true;
      alternative.hidden = false;
      inspector.hidden = true;
      backButton.hidden = true;
      legend.textContent = "";
      alternative.innerHTML = `<div class="flow-scope-notice" role="status"><h2>${esc(scopeNotice.label)}</h2>
        <p>${scopeNotice.ambiguous ? "The counterpart is ambiguous" : "No counterpart is recorded"} in this view. Your original location is retained.</p>
        <button type="button">Open nearest scope</button></div>`;
      alternative.querySelector("button").addEventListener("click", () => {
        rememberNavigationState();
        umlPath = scopeNotice.nearestPath;
        scopeNotice = null;
        render(); fit(); focusCurrentLevel();
      });
      return;
    }
    if (context) {
      renderArchitectureGraph(context);
      return;
    }
    viewButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.flowView === viewMode)));
    canvas.hidden = true;
    alternative.hidden = false;
    inspector.hidden = true;
    backButton.hidden = true;
    breadcrumb.textContent = "";
    legend.textContent = "";
    alternative.innerHTML = `<h2>${viewMode === "diagram" ? "Observed architecture unavailable" : "Independent Target unavailable"}</h2><p>${esc(DATA.unavailable || "No authenticated Target graph is recorded. Rendering does not reconstruct Target intent from unchecked records.")}</p>`;
  }

  toolbar.hidden = false;
  root.querySelector(".flow-views").hidden = false;
  violationFocus.hidden = false;
  violationFocus.classList.add("flow-graph-filter");
  violationsOnly.addEventListener("change", () => { positions = {}; render(); fit(); });
  viewButtons.forEach((button) => button.addEventListener("click", () => switchArchitectureView(button.dataset.flowView)));
  backButton.addEventListener("click", leaveArchitectureGraph);
  openSelectedButton.addEventListener("click", () => {
    if (umlSelection?.type === "node") { openArchitectureEntity(umlSelection.id); fit(); }
  });
  focusInput.addEventListener("change", () => { focusLabel = focusInput.value || null; positions = {}; render(); fit(); });
  elementKindInput.addEventListener("change", () => { elementKind = elementKindInput.value || null; focusLabel = null; positions = {}; render(); fit(); });
  legend.addEventListener("click", (event) => {
    const button = event.target.closest("[data-relationship-kind]");
    if (!button) return;
    relationshipKind = button.dataset.relationshipKind || null;
    positions = {};
    render(); fit();
  });
  resetFiltersButton.addEventListener("click", () => {
    focusLabel = null; relationshipKind = null; elementKind = null; umlSelection = null; positions = {};
    violationsOnly.checked = false;
    render(); fit();
  });
  fitButton.addEventListener("click", () => { positions = {}; render(); fit(); });
  overviewButton.addEventListener("click", () => { positions = {}; render(); fit(); });
  zoomOutButton.addEventListener("click", () => zoomBy(1 / 1.2));
  zoomInButton.addEventListener("click", () => zoomBy(1.2));
  zoom100Button.addEventListener("click", () => { transform.k = 1; diagramOrigin = null; sizeDiagram(); });
  svg.addEventListener("pointerdown", (event) => {
    if (!event.isPrimary || event.button !== 0 || event.target.closest(".node, .hit")) return;
    capturePointer(svg, event);
    panState = { x: event.clientX, y: event.clientY, left: canvas.scrollLeft, top: canvas.scrollTop };
    event.preventDefault();
  });
  svg.addEventListener("pointermove", (event) => {
    if (panState) {
      canvas.scrollLeft = panState.left - event.clientX + panState.x;
      canvas.scrollTop = panState.top - event.clientY + panState.y;
    }
    if (dragState) {
      positions[dragState.label] = { x: dragState.start.x + (event.clientX - dragState.x) / transform.k,
        y: dragState.start.y + (event.clientY - dragState.y) / transform.k };
      dragState.moved = Math.max(dragState.moved, Math.hypot(event.clientX - dragState.x, event.clientY - dragState.y));
      render();
    }
  });
  svg.addEventListener("pointerup", (event) => {
    if (dragState) {
      const slack = { mouse: 3, pen: 6, touch: 12 }[dragState.pointerType] ?? 12;
      const id = dragState.moved <= slack ? dragState.label : null;
      dragState = null;
      skipSvgClick = true;
      if (id) {
        const doubled = lastPointerTap?.id === id && event.timeStamp - lastPointerTap.timeStamp <= 500;
        lastPointerTap = doubled ? null : { id, timeStamp: event.timeStamp };
        if (doubled) { openArchitectureEntity(id); fit(); }
        else selectArchitectureSubject("node", id);
      }
    }
    if (panState) {
      skipSvgClick = Math.hypot(event.clientX - panState.x, event.clientY - panState.y) > 3;
      panState = null;
    }
  });
  svg.addEventListener("pointercancel", () => { dragState = null; panState = null; lastPointerTap = null; });
  svg.addEventListener("click", (event) => {
    if (skipSvgClick) { skipSvgClick = false; return; }
    if (!event.target.closest(".node, .hit")) { umlSelection = null; render(); }
  });
  svg.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { umlSelection = null; render(); }
  });
  fullscreenButton.addEventListener("click", async () => {
    if (root.dataset.expanded) {
      restoreExpansion();
      return;
    }
    const current = document.activeElement;
    try {
      if (root.requestFullscreen) {
        await root.requestFullscreen();
        return;
      }
    } catch {
      // A browser or embedding policy can deny the direct request.
    }
    expansionRestore = {
      focus: current,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      bodyOverflow: document.body.style.overflow,
      inert: [...document.querySelectorAll("main > *")].filter((element) =>
        !element.contains(root)).map((element) => [element, element.inert]),
    };
    expansionRestore.inert.forEach(([element]) => { element.inert = true; });
    document.body.style.overflow = "hidden";
    root.dataset.expanded = "fallback";
    root.setAttribute("aria-modal", "true");
    root.setAttribute("role", "dialog");
    fullscreenButton.textContent = "Restore";
    expandStatus.textContent = "Expanded in this window";
    expandStatus.hidden = false;
    fullscreenButton.focus({ preventScroll: true });
  });
  document.addEventListener("fullscreenchange", updateFullscreenState);
  root.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && root.dataset.expanded === "native") {
      event.preventDefault();
      event.stopPropagation();
      document.exitFullscreen?.();
    } else if (event.key === "Escape" && root.dataset.expanded === "fallback") {
      event.preventDefault();
      event.stopPropagation();
      restoreExpansion();
    } else if (event.key === "Tab" && root.dataset.expanded === "fallback") {
      const focusable = [...root.querySelectorAll("button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex='0']")]
        .filter((element) => !element.hidden && element.getClientRects().length);
      const first = focusable[0];
      const last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last?.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first?.focus();
      }
    }
  }, true);


  detailsToggle.addEventListener("click", () => { setTargetDetails(!targetDetailsOpen); render(); fit(); });
  render();
  fit();
  window.addEventListener("resize", () => { sizeDiagram(); });

})();
