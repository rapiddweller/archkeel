"use strict";
// One report model, scene projection and UML renderer for every architecture view.
(function () {
  const root = document.getElementById("flow");
  const dataNode = document.getElementById("flow-data");
  if (!root || !dataNode) return;
  const flowHeading = document.getElementById("flow-heading");
  flowHeading.tabIndex = -1;
  const DATA = JSON.parse(dataNode.textContent);
  const REPORT_SCENE = window.ArchkeelReportScene.create(DATA);
  const REPORT_LAYOUT = window.ArchkeelReportLayout;
  const ATLAS = REPORT_SCENE.atlas;
  const NAV = DATA.navigation || null;
  // AD-734: the one view state of the Explorer. A user action is one dispatch(action); the action
  // changes S, and render() draws S. report-canvas.js keeps its presentation choices here too.
  const S = {
    view: DATA.initial_view || "diagram",
    path: [],
    content: null, selection: null, cell: null, module: null, hint: null, allHints: false,
    details: false, explore: false,
    perspective: "language", pinnedTag: null, drawer: null, overlay: null, pop: null,
    theme: document.documentElement.dataset.theme || "dark", expanded: null,
  };
  let routeReady = false, routeNotice = null;
  let pendingAtlasFindingHash = null;
  // E5 (issue 1451): every payload of the core has an atlas; the Explorer has no other branch.
  if (!["1.0.0", "1.2.0"].includes(DATA.schema_version) || !ATLAS) {
    root.textContent = "Unsupported architecture report schema.";
    return;
  }
  let positions = Object.create(null), diagramOrigin = null, sizedPositions = positions;
  let layoutPending = false, pendingLayoutFit = false;
  let pendingLayoutFitOverview = false, layoutGeneration = 0;
  const layoutPromises = new Map();
  let scrollRemainderX = 0, scrollRemainderY = 0;
  let renderedScene = null, renderedRoutes = [], focusLabel = null, relationshipKind = null, elementKind = null;
  let showAllModuleElements = false, showExternalSymbols = false;
  let transform = { k: 1 };
  let panState = null, expansionRestore = null;
  let panOffset = { x: 0, y: 0 };
  let skipSvgClick = false;
  const CARD = { w: 200, h: 92 };
  const cardHeights = new Map();
  const GAP = 34;
  const ROW_GAP = 90;
  const TARGET_RESIDUAL_GAP = 20;
  const LANE_GAP = 11;
  const ROUTING_WARNING = "Renderer layout warning: no clear route around a card or frame header; architectural status is unchanged.";

  // The one place an EdgeState maps to a human label. Edge and chip elements already take their
  // color and dash pattern from the CSS class `edge ${state}` / `chip ${state}` (see
  // archkeel-report.css), so the legend swatches below reuse those same classes instead of a
  // second, hand-written color/dash list.

  const svg = root.querySelector(".flow-graph");
  for (const kind of ["calls", "imports", "references", "creates", "instance_of", "mixes_in"]) {
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
  filters.open = false;
  legendPanel.open = !compactControls.matches;
  compactControls.addEventListener("change", () => {
    filters.open = false;
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
  const elementIndex = document.createElement("section");
  elementIndex.className = "flow-element-index";
  elementIndex.hidden = true;
  const useSummary = document.createElement("button");
  useSummary.type = "button";
  useSummary.className = "flow-fit flow-use-summary flow-graph-filter";
  useSummary.hidden = true;
  toolbar.appendChild(useSummary);
  canvas.before(elementIndex);
  useSummary.addEventListener("click", () => {
    showExternalSymbols = !showExternalSymbols;
    positions = Object.create(null);
    render(); fit();
  });
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
  const detailsToggle = document.createElement("button");
  detailsToggle.type = "button";
  detailsToggle.className = "flow-fit flow-details-toggle";
  detailsToggle.dataset.flowDetailsToggle = "";
  detailsToggle.setAttribute("aria-controls", inspector.id);
  detailsToggle.setAttribute("aria-expanded", "false");
  detailsToggle.textContent = "Details";
  toolbar.appendChild(detailsToggle);
  const unassignedCodeButton = document.createElement("button");
  unassignedCodeButton.type = "button";
  unassignedCodeButton.className = "flow-fit flow-unassigned-code";
  unassignedCodeButton.hidden = true;
  toolbar.appendChild(unassignedCodeButton);
  unassignedCodeButton.addEventListener("click", () => {
    S.selection = null;
    setTargetDetails(true);
    render();
  });
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
    positions = Object.create(null);
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
    .getPropertyValue("--font-sans").replace(/\s+/g, " ").trim();
  const monoFontFamily = getComputedStyle(document.documentElement)
    .getPropertyValue("--font-mono").replace(/\s+/g, " ").trim();
  const measureCanvas = document.createElement("canvas");
  const measureText = measureCanvas.getContext("2d");

  const DASH_RATIOS = { violation: [2.4, 1.8], undecided: [0.55, 1.5], observed: [1.6, 1.4] };

  function setTargetDetails(open) {
    S.details = open;
    root.dataset.detailsOpen = String(open);
    detailsToggle.setAttribute("aria-expanded", String(open));
    detailsToggle.setAttribute("aria-label", "Details " + (open ? "open" : "closed"));
    inspector.hidden = !open;
    if (open) root.dispatchEvent(new CustomEvent("archkeel:inspect"));
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
    for (const word of text.split(/(\s+)|(?<=[_/])|(?<=[a-z])(?=[A-Z])/).filter(Boolean)) {
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
      root.dataset.expanded = S.expanded = "native";
      fullscreenButton.textContent = "Back to report";
      fullscreenButton.setAttribute("aria-label", "Back to report");
      expandStatus.hidden = true;
    } else if (root.dataset.expanded === "native") {
      restoreExpansion();
    }
    sizeDiagram();
  }

  function syncExpansionInert() {
    if (root.dataset.expanded !== "fallback") return;
    for (const element of document.querySelectorAll("main > *")) {
      if (!element.contains(root) && !expansionRestore.inert.some(([saved]) => saved === element)) {
        expansionRestore.inert.push([element, element.inert]);
      }
    }
    for (const [element, inert] of expansionRestore.inert) {
      element.inert = root.contains(element) ? inert : true;
    }
  }

  function restoreExpansion() {
    if (document.fullscreenElement === root) {
      document.exitFullscreen?.();
      return;
    }
    if (!root.dataset.expanded) return;
    delete root.dataset.expanded;
    S.expanded = null;
    sizeDiagram();
    root.removeAttribute("aria-modal");
    root.removeAttribute("role");
    document.body.style.overflow = expansionRestore.bodyOverflow;
    window.scrollTo(expansionRestore.scrollX, expansionRestore.scrollY);
    for (const [element, inert] of expansionRestore.inert) element.inert = inert;
    const focus = expansionRestore.focus;
    expansionRestore = null;
    fullscreenButton.textContent = "Fullscreen";
    fullscreenButton.setAttribute("aria-label", "Fullscreen");
    expandStatus.hidden = true;
    if (focus?.isConnected) focus.focus({ preventScroll: true });
  }

  function cardHeight(id) {
    return cardHeights.get(id) ?? CARD.h;
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
    } else if (["class", "mixin", "enum"].includes(kind)) {
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
      rx: ["class", "interface", "enum", "mixin"].includes(node.kind) ? "2" : "8",
    }));
    group.appendChild(el("path", { class: "uml-kind-accent", d: `M16,2 H${CARD.w - 16}` }));
    if (node.violation) group.appendChild(el("rect", {
      class: "tick violated", width: "3", height: String(cardHeight(node.id) - 24), x: "0", y: "12",
    }));
    const kind = el("text", { class: "stereotype", x: "16", y: "19" });
    const stereotype = node.kind === "class" && node.entity?.modifiers.includes("mixin")
      ? "mixin class" : node.kind === "enum" ? "enumeration"
        : node.kind === "enum_literal" ? "enumeration literal" : node.kind;
    kind.textContent = `«${stereotype}»${node.outside ? " · outside" : ""}`;
    group.appendChild(kind);
    const name = createWrappedText(node.label, {
      class: "label", x: "16", y: "37",
      "text-decoration": node.entity?.modifiers.includes("static") ? "underline" : "none",
    },
      CARD.w - 48, `600 14px ${sansFontFamily}`, 18);
    group.appendChild(name);
    const nameLines = wrapText(node.label, CARD.w - 48, `600 14px ${sansFontFamily}`).length;
    group.appendChild(createWrappedText(node.meta, {
      class: "meta", x: "16", y: String(42 + nameLines * 18),
      "text-decoration": node.entity?.modifiers.includes("static") ? "underline" : "none",
    }, CARD.w - 32, `12px ${monoFontFamily}`, 14));
    for (const section of umlCompartments(node)) {
      group.appendChild(el("path", { class: "uml-divider", d: `M0,${section.top} H${CARD.w}` }));
      const heading = el("text", { class: "uml-compartment-title", x: "12", y: String(section.top + 15) });
      heading.textContent = section.label;
      group.appendChild(heading);
      let y = section.top + 32;
      for (const line of section.lines) {
        group.appendChild(createWrappedText(line.text, {
          class: "uml-member", x: "12", y: String(y),
          "text-decoration": line.static ? "underline" : "none",
        }, CARD.w - 24, `11px ${monoFontFamily}`, 14));
        y += wrapText(line.text, CARD.w - 24, `11px ${monoFontFamily}`).length * 14;
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
        height + wrapText(line.text, CARD.w - 24, `11px ${monoFontFamily}`).length * 14, 0);
      const compartment = { ...section, top, bottom };
      top = bottom + 8;
      return compartment;
    });
  }

  function drawUmlFrame(frame, singleRoot) {
    const box = frame.bounds;
    const frameKind = frame.kind || "package";
    const group = el("g", {
      class: `node uml-frame${singleRoot && !frame.parent ? " package-overview" : ""}`,
      tabindex: "0", role: "button", "data-uml-id": frame.id, "data-uml-kind": frameKind,
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
    frameHeaderText(group, frameKind === "component" ? "«component»" : "«package»",
      name, box.left + 56, box.top + 37);
    group.setAttribute("aria-label", frame.tooltip);
    const title = el("title");
    title.textContent = frame.tooltip;
    group.appendChild(title);
    return group;
  }

  function drawUmlEdge(edge, route) {
    edge.routingWarning = Boolean(route.routingWarning);
    const warning = edge.routingWarning ? ` ${ROUTING_WARNING}` : "";
    const group = el("g", { class: `edge ${edge.state}${edge.edgeClass ? ` ${edge.edgeClass}` : ""}`, "data-uml-id": edge.id,
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

  function renderUmlScene(scene, bindings, preparedRoutes = null) {
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
    const layoutRoutes = preparedRoutes || REPORT_LAYOUT.routeUmlRelationships({
      positions,
      nodeSizes: Object.fromEntries(scene.nodes.map((node) => [node.id, { width: CARD.w, height: cardHeight(node.id) }])),
      edges: scene.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target,
        relationshipKind: edge.relationshipKind })),
      frames: Object.fromEntries(scene.frames.map((frame) => [frame.id, frame.bounds])),
      cardWidth: CARD.w, gap: GAP, laneGap: LANE_GAP, rowGap: ROW_GAP,
    });
    const edgeById = new Map(scene.edges.map((edge) => [edge.id, edge]));
    const routes = layoutRoutes.map((route) => ({ ...route,
      edge: route.edge || edgeById.get(route.edgeId) }));
    renderedRoutes = routes;
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
    // Runs after the caller finished its synchronous decoration of this scene.
    queueMicrotask(() => root.dispatchEvent(new CustomEvent("archkeel:rendered")));
    return routes;
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

  function selectArchitectureSubject(type, id) {
    S.module = S.view !== "target" && REPORT_SCENE.atlasModuleById(id) ? id : null; S.cell = null;
    S.selection = { type, id };
    setTargetDetails(true);
    nodeLayer.querySelectorAll("[data-uml-id]").forEach((node) => {
      const selected = type === "node" && node.dataset.umlId === id;
      node.classList.toggle("selected", selected);
      node.setAttribute("aria-pressed", String(selected));
    });
    edgeLayer.querySelectorAll(".hit").forEach((hit) => hit.setAttribute("aria-pressed",
      String(type === "edge" && hit.parentElement.dataset.umlId === id)));
    emphasizeUmlScene(S.selection);
    syncRoute();
    atlasSheet(atlasLevel());
    updateOpenSelected();
  }


  function openArchitectureEntity(id) {
    const module = renderedScene?.nodes.find((node) => node.id === id)?.module;
    if (module) openAtlasModule(module.id);
    else openAtlasComponent(id, renderedScene?.grouped ? "modules" : null);
  }


  function readRoute() {
    const query = new URLSearchParams(location.search);
    positions = Object.create(null);
    const { notice, details, ...next } = fromQuery(query);
    routeNotice = notice;
    Object.assign(S, next);
    setTargetDetails(details);
  }


  // AD-734: the URL of a view state, and the view state of a URL. toQuery(fromQuery(q)) is q for a
  // query that toQuery wrote. A default is left out: the language perspective, Details that follow
  // the selection (open with a selected box or cell, closed without), no drawer.
  const VIEWS = ["diagram", "target", "diff"], DRAWERS = ["overview", "objects"];
  const PERSPECTIVES = window.ArchkeelReportScene.perspectives;

  function atlasLevelOf(path) {
    return ATLAS.levels.find((level) => level.parent_id === (path.at(-1)?.id || null)) || ATLAS.levels[0];
  }

  function stateSelected(state) {
    return state.module || (state.selection?.type === "node" ? state.selection.id : null);
  }

  function toQuery(state) {
    const query = new URLSearchParams();
    if (state.path.length) query.set("scope", state.path.at(-1).id);
    if (atlasHasChoice(atlasLevelOf(state.path), state.view) && state.content) query.set("content", state.content);
    query.set("view", state.view);
    if (state.perspective !== "language") query.set("perspective", state.perspective || "none");
    const selected = stateSelected(state);
    if (selected) query.set("selected", selected);
    if (state.cell !== null) query.set("cell", String(state.cell));
    if (state.details !== (Boolean(selected) || state.cell !== null)) query.set("details", state.details ? "open" : "closed");
    if (state.drawer) query.set("drawer", state.drawer);
    return query;
  }

  function fromQuery(query) {
    const view = VIEWS.includes(query.get("view")) ? query.get("view") : "diagram";
    const component = query.get("component");
    const scope = query.get("scope") || (component === "unassigned" ? null : component) || query.get("module");
    const known = ATLAS.levels.some((level) => level.parent_id === scope);
    const notice = scope && !known
      ? { field: "scope", requested: scope, message: "Requested component scope is not recorded in this snapshot." } : null;
    const path = known ? REPORT_SCENE.componentRoute(scope).map((item) => ({ id: item.id, origin: "observed" })) : [];
    const level = atlasLevelOf(path);
    const content = atlasHasChoice(level, view) && ["components", "modules"].includes(query.get("content"))
      ? query.get("content") : component === "unassigned" || query.has("module") ? "modules" : null;
    const requested = query.get("selected") || query.get("module");
    const selection = level.component_ids.includes(requested)
      || REPORT_SCENE.atlasModules(level, view).some((item) => item.id === requested) ? { type: "node", id: requested } : null;
    const module = view !== "target" && level.modules.some((item) => item.id === requested) ? requested : null;
    const number = Number(query.get("cell"));
    const cell = query.has("cell") && view !== "target" && level.cells.includes(number) ? number : null;
    const asked = query.get("perspective");
    const perspective = asked === "none" ? null : Object.hasOwn(PERSPECTIVES, asked) ? asked : "language";
    const drawer = DRAWERS.includes(query.get("drawer")) ? query.get("drawer") : null;
    const details = query.get("details") === "open" || query.get("details") !== "closed"
      && (Boolean(selection || module) || cell !== null);
    return { view, path, content, selection, module, cell, perspective, drawer, details, notice };
  }

  // The state for an agent or a test: `data-state` on the Explorer and ArchkeelFlow.state().
  function stateView() {
    const level = atlasLevel();
    const content = level.component_ids.length
      ? S.content === "modules" && REPORT_SCENE.atlasModules(level, S.view).length ? "modules" : "components" : "modules";
    return { view: S.view, scope: S.path.at(-1)?.id ?? null, path: S.path.map((entry) => entry.id), content,
      selection: S.selection?.type === "node" ? S.selection.id : null,
      edge: S.selection?.type === "edge" ? S.selection.id : null,
      module: S.module, cell: S.cell, hint: S.hint, details: S.details, drawer: S.drawer, overlay: S.overlay,
      pop: S.pop, perspective: S.perspective, pinnedTag: S.pinnedTag, theme: S.theme, expanded: S.expanded,
      notice: routeNotice?.message ?? null };
  }

  function publishState() { root.dataset.state = JSON.stringify(stateView()); }

  // AD-734: a navigation (a level, up, the view, the content) adds a history entry; any other
  // change (selection, Details, drawer, perspective, theme) replaces the current entry. So Back
  // goes back one level.
  let historyMode = "replace";
  function navigate() { historyMode = "push"; }

  function syncRoute(replace = historyMode !== "push") {
    document.querySelectorAll("[data-atlas-component-route]").forEach((link) => {
      link.href = atlasComponentHref(link.dataset.atlasComponentRoute || null);
    });
    publishState();
    if (!NAV || !routeReady || routeNotice || !["file:", "http:", "https:"].includes(location.protocol)) return;
    const query = toQuery(S);
    const permissionHash = [...REPORT_SCENE.boundaryPermissions.declared,
      ...REPORT_SCENE.boundaryPermissions.applied].some((row) => location.hash === `#${encodeURIComponent(row.id)}`)
      ? location.hash : "";
    const next = `${location.pathname}?${query}${permissionHash}`;
    const currentQuery = new URLSearchParams(location.search);
    currentQuery.sort(); query.sort();
    // Unchanged routes must keep existing finding anchors.
    if (currentQuery.toString() !== query.toString())
      if (replace) history.replaceState(null, "", next);
      else history.pushState(null, "", next);
  }

  // E2: archkeel-theme.js owns the theme (the header switch, localStorage, the OS default). The
  // Explorer follows data-theme and keeps the theme out of the URL and the history.
  function followTheme() {
    const light = document.documentElement.dataset.theme === "light";
    S.theme = light ? "light" : "dark";
    const button = document.querySelector(".theme-toggle");
    if (button) {
      button.textContent = light ? "☾" : "☀";
      button.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
    }
    publishState();
  }
  new MutationObserver(followTheme)
    .observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  followTheme();

  // A theme action goes through the owner: its own header button stores and shows the choice.
  function setTheme(theme) {
    const owner = document.querySelector(`[data-ak-theme="${theme}"]`);
    if (owner) owner.click();
    else document.documentElement.dataset.theme = theme;
  }

  function renderRouteNotice() {
    canvas.hidden = true; alternative.hidden = false; setTargetDetails(true);
    filters.hidden = true; elementKindControl.hidden = true; legend.textContent = "";
    openSelectedButton.disabled = true;
    root.querySelector(".flow-explore").hidden = true;
    root.dataset.view = S.view;
    viewButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.flowView === S.view)));
    flowHeading.textContent = "Requested scope unavailable";
    alternative.innerHTML = `<div class="flow-scope-notice" role="status"><h3>Requested scope unavailable</h3><p>${esc(routeNotice.message)}</p><p>Requested ID: <code>${esc(routeNotice.requested)}</code></p><p>The requested URL is retained until you choose a recorded location.</p><button type="button">Open architecture map</button></div>`;
    alternative.querySelector("button").onclick = () => { routeNotice = null; render(); fit(); };
    architectureNavigation();
    inspectorContent.innerHTML = '<div class="kicker">Fact sheet</div><p>Choose a recorded architecture scope.</p>';
    root.dataset.layoutState = "ready";
    publishState();
  }

  function architectureNavigation() {
    // E3: each crumb names itself in full (a title for a shortened one); the current crumb says so.
    // E4: the page of a part names its system after its root crumb, as a link to the system page.
    const crumbs = [NAV?.part_title || ATLAS.repository, ...S.path.map((entry) => REPORT_SCENE.atlasComponent(entry.id)?.label || entry.id)];
    const system = !NAV?.part_title ? "" : NAV.system_href
      ? `<span> of </span><a href="${esc(NAV.system_href)}" title="${esc(NAV.system_title)}">${esc(NAV.system_title)}</a>`
      : `<span> of ${esc(NAV.system_title)}</span>`;
    breadcrumb.innerHTML = crumbs.map((label, depth) => `${depth ? "<span> / </span>" : ""}<button type="button" data-atlas-depth="${depth}" title="${esc(label)}"${depth === crumbs.length - 1 ? ' aria-current="page"' : ""}><span>${esc(label)}</span></button>${depth ? "" : system}`).join("");
    breadcrumb.querySelectorAll("button").forEach((button) => button.onclick = () =>
      dispatch({ type: "goToDepth", depth: Number(button.dataset.atlasDepth) }));
    backButton.hidden = !S.path.length; backButton.textContent = "Back to components";
  }


  const boundaryPermissionGroups = new Map();
  let boundaryAuditMarkup = "";

  function boundaryPermissionMarkup(scope = null, related = new Set(), edge = false) {
    const permissions = REPORT_SCENE.boundaryPermissions;
    boundaryPermissionGroups.clear(); boundaryAuditMarkup = "";
    if (!permissions || edge) return "";
    const touches = (row) => scope === null || row.entity_ids?.some((id) => related.has(id))
      || row.component_ids?.includes(scope) || row.routes?.some((route) => route.module_id === scope);
    const inScope = (row) => touches(row) || S.view === "diff" && (row.data
      ? (permissions.declared || []).some((entry) => entry.id === row.declaration_id && touches(entry))
      : (permissions.applied || []).some((entry) => entry.declaration_id === row.id && touches(entry)));
    const kinds = [["declared", "Declared boundary permissions"], ["applied", "Applied boundary permissions"]]
      .filter(([kind]) => kind === "declared" ? S.view !== "diagram" : S.view !== "target");
    const sections = kinds.map(([kind, title]) =>
      boundaryPermissionSection((permissions[kind] || []).filter(inScope), title, kind));
    if (location.hash) queueMicrotask(() => openBoundaryPermissionHash());
    if (scope !== null) return sections.join("");
    const counts = kinds.map(([kind]) => `${(permissions[kind] || []).length} ${kind}`).join(" · ");
    boundaryAuditMarkup = sections.join("");
    return `<section class="boundary-permissions"><h3>Boundary permissions</h3>
      <p class="boundary-permission-counts">${counts}</p>
      <p>Recorded permissions do not establish rule status. Select a scope for relevant records.</p>
      <details data-boundary-audit><summary>Complete boundary permission audit · ${counts}</summary></details></section>`;
  }

  function boundaryPermissionSection(rows, title, kind) {
    if (!rows.length) return "";
    const groups = new Map();
    for (const row of rows) {
      const mapped = row.entity_ids?.length || row.component_ids?.length;
      const rule = row.rule_id || (row.rule_ids || []).join(" · ") || "Rule unavailable";
      const label = mapped ? rule : "Unmapped boundary permission audit";
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(row);
    }
    return `<section class="boundary-permissions"><h3>${title} · ${rows.length}</h3>${[...groups].map(([label, records]) => {
      const key = String(boundaryPermissionGroups.size);
      boundaryPermissionGroups.set(key, { rows: records, applied: kind === "applied" });
      return `<details data-boundary-group="${key}" data-boundary-kind="${kind}"><summary>${esc(label)} · ${REPORT_SCENE.countLabel(records.length, "record")}</summary></details>`;
    }).join("")}</section>`;
  }

  function boundaryPermissionRecordMarkup(row, applied) {
    const selector = applied ? row.data || {} : row;
    return `<details data-boundary-permission="${esc(row.id)}" id="${esc(row.id)}"><summary>${esc(selector.qualified_name || row.title || "Selector unavailable")} · ${esc(selector.position || "Position unavailable")}</summary></details>`;
  }

  function boundaryPermissionDetails(row, applied) {
    const permissions = REPORT_SCENE.boundaryPermissions;
    const routeLink = (route) => {
      const query = new URLSearchParams({component: route.component_id || "unassigned",
        view: S.view, origin: route.origin});
      if (route.module_id) query.set("module", route.module_id);
      if (route.scope_id) query.set("scope", route.scope_id);
      query.set("selected", route.entity_id);
      query.set("return_view", S.view);
      if (atlasLevel().parent_id) query.set("return_scope", atlasLevel().parent_id);
      return `<a href="${esc(`${ATLAS.detail_page || location.pathname}?${query}`)}">${esc(route.label)}</a>`;
    };
    const selector = applied ? row.data || {} : row;
    const declaration = applied && (permissions.declared || []).find((item) => item.id === row.declaration_id);
    const declarationRoute = declaration?.routes?.[0];
    const declarationOwner = declarationRoute?.component_id || declaration?.component_ids?.[0];
    const declarationQuery = new URLSearchParams({component: declarationOwner || "unassigned", origin: "declared", view: "target"});
    if (declarationRoute?.module_id) declarationQuery.set("module", declarationRoute.module_id);
    if (declarationRoute?.scope_id) declarationQuery.set("scope", declarationRoute.scope_id);
    if (declarationRoute?.entity_id) declarationQuery.set("selected", declarationRoute.entity_id);
    const declarationHref = `${ATLAS.detail_page || location.pathname}?${declarationQuery}#${encodeURIComponent(row.declaration_id || "")}`;
    const keys = ["qualified_name", "position", "field_path", "annotation", "container_depth", "mapping_depth", "literal_mapping_arm", "native_mapping", ...(applied ? ["observed_container_depth"] : [])];
    const bindingRows = ["alias_body", "key_alias_body"].flatMap((name) => {
      const binding = selector[name];
      return !Object.hasOwn(selector, name) ? []
        : binding && typeof binding === "object" && !Array.isArray(binding) && Object.keys(binding).length
          ? Object.entries(binding).map(([key, value]) => [`${name}.${key}`, value])
          : [[name, binding]];
    });
    const selectorRows = [...keys.filter((key) => Object.hasOwn(selector, key)).map((key) => [key, selector[key]]), ...bindingRows];
    const ownerLinks = !row.routes?.length ? (row.component_ids || []).map((id) => {
      const query = new URLSearchParams({component: id, origin: "declared", view: "target"});
      return `<a href="${esc(`${ATLAS.detail_page || location.pathname}?${query}`)}">Declared owning component</a>`;
    }).join(" · ") : "";
    return `<dl class="kv">${selectorRows.map(([key, value]) => `<dt>${esc(key === "observed_container_depth" ? "Observed container depth" : key)}</dt><dd><code>${esc(typeof value === "string" ? value : JSON.stringify(value))}</code></dd>`).join("")}</dl>
      <p>${esc(row.rationale || "Rationale unavailable")} · Decided by ${esc(row.decided_by || "Unavailable")}</p>
      ${applied && selector.accepted_opacity === true ? "<p>Accepted opacity; type closure remains unproven.</p>" : ""}
      <p>Recorded ID <code>${esc(row.id)}</code></p>
      ${applied ? `<p>${esc(row.title || "Recorded applied permission")}</p><p>Declaration: ${row.declaration_id ? declarationOwner ? `<a href="${esc(declarationHref)}">${esc(row.declaration_id)}</a>` : `<code>${esc(row.declaration_id)}</code> · Navigation unavailable` : "Unavailable or ambiguous"}</p>` : `<p>Rule <code>${esc(row.rule_id)}</code> · Contract scope <code>${esc(row.contract_scope_id ?? "root")}</code> · Source <code>${esc(row.source ?? "Unavailable")}</code></p>`}
      ${["rule_ids", "fact_ids", "evidence_ids", "provenance"].map((key) => `<p>${esc(key)}: ${(row[key] || []).map(esc).join(" · ") || "Not recorded"}</p>`).join("")}
      <p>${(row.locations || []).map((item) => esc(`${item.file || "Location unavailable"}${item.line != null ? `:${item.line}` : ""} · ${item.id}`)).join("<br>") || "Source evidence location unavailable"}</p>
      <p>${(row.routes || []).map(routeLink).join(" · ")}${ownerLinks || ""}</p>
      ${!row.routes?.length && !row.component_ids?.length ? "<p>Navigation unavailable or ambiguous; retained in root audit.</p>" : ""}
      <p><a href="${esc(ATLAS.architecture_href || NAV?.architecture_href || "architecture.json")}">Complete audit JSON</a></p>
    `;
  }

  function fillBoundaryPermissionGroup(group, limit = 20, requestedId = null) {
    const state = boundaryPermissionGroups.get(group.dataset.boundaryGroup);
    if (!state) return;
    let list = group.querySelector("[data-boundary-record-list]");
    if (!list) {
      list = document.createElement("div"); list.dataset.boundaryRecordList = ""; group.appendChild(list);
    }
    const records = state.rows.slice(Number(group.dataset.boundaryLimit || 0), limit);
    if (requestedId) {
      const requested = state.rows.find((row) => row.id === requestedId);
      if (requested) records.push(requested);
    }
    for (const row of records) {
      if (!document.getElementById(row.id)) list.insertAdjacentHTML("beforeend", boundaryPermissionRecordMarkup(row, state.applied));
    }
    group.dataset.boundaryLimit = String(Math.min(limit, state.rows.length));
    let more = group.querySelector("[data-boundary-more]");
    if (limit < state.rows.length) {
      if (!more) {
        more = document.createElement("button"); more.type = "button"; more.className = "flow-fit";
        more.dataset.boundaryMore = ""; group.appendChild(more);
      }
      more.textContent = `Show next ${Math.min(20, state.rows.length - limit)} records · ${state.rows.length - limit} remaining`;
    } else if (more) {
      const hadFocus = document.activeElement === more;
      more.remove();
      if (hadFocus) list.lastElementChild?.querySelector("summary")?.focus();
    }
  }

  function fillBoundaryPermissionDetails(record) {
    if (record.dataset.boundaryLoaded) return;
    const state = boundaryPermissionGroups.get(record.closest("[data-boundary-group]")?.dataset.boundaryGroup);
    const row = state?.rows.find((item) => item.id === record.dataset.boundaryPermission);
    if (!row) return;
    record.insertAdjacentHTML("beforeend", boundaryPermissionDetails(row, state.applied));
    record.dataset.boundaryLoaded = "true";
  }

  function fillBoundaryPermissionAudit(audit) {
    if (audit.dataset.boundaryLoaded) return;
    audit.insertAdjacentHTML("beforeend", boundaryAuditMarkup);
    audit.dataset.boundaryLoaded = "true";
  }

  function openBoundaryPermissionHash(requestedId = null) {
    let id = requestedId;
    if (id === null) {
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { return false; }
    }
    const entry = [...boundaryPermissionGroups].find(([, state]) => state.rows.some((row) => row.id === id));
    if (!entry) return false;
    const audit = inspectorContent.querySelector("[data-boundary-audit]");
    if (audit) { audit.open = true; fillBoundaryPermissionAudit(audit); }
    const group = inspectorContent.querySelector(`[data-boundary-group="${entry[0]}"]`);
    if (!group) return false;
    group.open = true;
    fillBoundaryPermissionGroup(group, Number(group.dataset.boundaryLimit || 20), id);
    const record = document.getElementById(id);
    record.open = true; fillBoundaryPermissionDetails(record); setTargetDetails(true);
    requestAnimationFrame(() => { if (record.isConnected) record.scrollIntoView(); });
    return true;
  }

  inspectorContent.addEventListener("toggle", (event) => {
    const target = event.target;
    if (!target.open) return;
    if (target.hasAttribute("data-boundary-audit")) fillBoundaryPermissionAudit(target);
    if (target.hasAttribute("data-boundary-group")) fillBoundaryPermissionGroup(target, Number(target.dataset.boundaryLimit || 20));
    if (target.hasAttribute("data-boundary-permission")) fillBoundaryPermissionDetails(target);
  }, true);
  inspectorContent.addEventListener("click", (event) => {
    const more = event.target.closest("[data-boundary-more]");
    if (!more) return;
    const group = more.closest("[data-boundary-group]");
    fillBoundaryPermissionGroup(group, Number(group.dataset.boundaryLimit) + 20);
  });

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
    const nextX = bounds.x - Math.max(padding,
      (canvas.clientWidth / transform.k - bounds.width) / 2);
    const nextY = bounds.y - padding;
    if (!diagramOrigin) {
      diagramOrigin = { x: nextX, y: nextY };
      scrollRemainderX = 0;
      scrollRemainderY = 0;
    }
    const scrollX = 0;
    const scrollY = 0;
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
    // Round outward so CSS pixel quantization cannot shrink fitted text.
    svg.style.width = `${Math.ceil(viewWidth * transform.k + horizontalBorder)}px`;
    svg.style.height = `${Math.ceil(viewHeight * transform.k + verticalBorder)}px`;
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
    markOverflow();
  }

  let maxFitScale = 1.4;
  // Below this scale the 12 px card text is too small to read (issue 1490): a fit stops here and
  // the canvas scrolls. Only an explicit "fit whole diagram" goes below it.
  const READABLE_SCALE = 0.85;
  let pendingLayoutFitWhole = false;
  function fit(overview = false, { whole = false } = {}) {
    if (layoutPending) {
      pendingLayoutFit = true;
      pendingLayoutFitOverview ||= overview;
      pendingLayoutFitWhole ||= whole;
      return;
    }
    const bounds = viewport.getBBox();
    if (!bounds.width || !bounds.height || !canvas.clientWidth || !canvas.clientHeight) return;
    // Member compartments need readable text; oversized content stays pannable.
    const minimumScale = overview ? whole ? 0 : READABLE_SCALE : 1;
    const widthScale = canvas.clientWidth / (bounds.width + 48);
    transform.k = renderedScene?.moduleOverview && !overview
      ? Math.max(READABLE_SCALE, Math.min(maxFitScale, widthScale, canvas.clientHeight / (bounds.height + 48)))
      : Math.max(minimumScale, Math.min(maxFitScale, widthScale, canvas.clientHeight / (bounds.height + 48)));
    panOffset = { x: 0, y: 0 };
    viewport.removeAttribute("transform");
    diagramOrigin = null;
    sizeDiagram();
    canvas.scrollLeft = 0;
    canvas.scrollTop = 0;
    if (!whole && (renderedScene?.componentOverview || renderedScene?.moduleOverview)
        && (canvas.scrollWidth > canvas.clientWidth + 1 || canvas.scrollHeight > canvas.clientHeight + 1)) {
      // Issue 1618: a diagram larger than the view at the readable zoom opens at its top-left box;
      // the faded edges and the hint say that it goes on.
      const first = renderedScene.nodes
        .filter((node) => positions[node.id])
        .sort((a, b) => positions[a.id].x + positions[a.id].y - positions[b.id].x - positions[b.id].y)[0];
      const position = first && positions[first.id];
      if (position) {
        canvas.scrollLeft = Math.max(0, (position.x - diagramOrigin.x - 24) * transform.k);
        canvas.scrollTop = Math.max(0, (position.y - diagramOrigin.y - 24) * transform.k);
      }
    }
    markOverflow();
  }

  // The sides of the canvas with more of the diagram beyond them (issue 1618).
  function markOverflow() {
    const more = [];
    if (canvas.scrollLeft > 1) more.push("left");
    if (canvas.scrollLeft + canvas.clientWidth < canvas.scrollWidth - 1) more.push("right");
    if (canvas.scrollTop > 1) more.push("top");
    if (canvas.scrollTop + canvas.clientHeight < canvas.scrollHeight - 1) more.push("bottom");
    const value = more.join(" ");
    if (root.dataset.overflow !== value) root.dataset.overflow = value;
  }
  canvas.addEventListener("scroll", markOverflow, { passive: true });

  function zoomBy(factor) {
    const minimumScale = renderedScene?.moduleOverview ? 0 : 0.1;
    transform.k = Math.min(2.4, Math.max(minimumScale, transform.k * factor));
    sizeDiagram();
  }

  // The content under the pointer stays under the pointer. Measured on the SVG box, so
  // centering of narrow diagrams and the pan offset are already included.
  function zoomAt(factor, clientX, clientY) {
    const before = svg.getBoundingClientRect();
    const x = (clientX - before.left) / transform.k, y = (clientY - before.top) / transform.k;
    zoomBy(factor);
    const after = svg.getBoundingClientRect();
    const dx = after.left + x * transform.k - clientX, dy = after.top + y * transform.k - clientY;
    const left = canvas.scrollLeft, top = canvas.scrollTop;
    canvas.scrollLeft += dx;
    canvas.scrollTop += dy;
    // Narrow diagrams cannot scroll; the remainder moves the existing pan offset instead.
    const restX = dx - (canvas.scrollLeft - left), restY = dy - (canvas.scrollTop - top);
    if (Math.abs(restX) > 0.5 || Math.abs(restY) > 0.5) {
      panOffset = { x: panOffset.x - restX / transform.k, y: panOffset.y - restY / transform.k };
      viewport.setAttribute("transform", `translate(${panOffset.x} ${panOffset.y})`);
    }
  }

  function focusCurrentLevel() {
    const subject = S.selection && svg.querySelector(`[data-uml-id="${CSS.escape(S.selection.id)}"]`);
    (subject?.querySelector(".hit") || subject || nodeLayer.querySelector(".node") || flowHeading)
      .focus({ preventScroll: true });
  }

  function updateOpenSelected() {
    // A module is the last level: selecting it shows all of its facts, so it has nothing to open.
    const component = S.selection && REPORT_SCENE.atlasComponent(S.selection.id);
    openSelectedButton.disabled = !component || !ATLAS.levels.some((level) => level.parent_id === S.selection.id);
    openSelectedButton.textContent = component ? `Open ${component.label}` : "Open selected";
  }

  function findingMarkup(findings) {
    return findings.length ? `<ul class="plain">${findings.map((item) => `<li class="${item.status === "FAIL" ? "violation-card" : "unknown-card"}"><strong>${esc(item.status)} · ${esc(item.title)}</strong><p><code>${item.rule_ids.map(esc).join(", ")}</code></p><p>${item.subjects.map(esc).join(", ")}</p></li>`).join("")}</ul>` : "<p>No recorded failures or UNKNOWN findings. This is not a completeness claim.</p>";
  }

  function switchArchitectureView(nextView) {
    // E3: the view of the page is not a new view: fullscreen and the key of the current view lay
    // the diagram out again and keep the selection.
    if (nextView === S.view) { relayout(); return; }
    navigate();
    S.view = nextView;
    if (nextView === "target") { S.cell = null; S.module = null; S.hint = null; }
    const level = atlasLevel();
    if (S.selection && !level.component_ids.includes(S.selection.id)
        && !REPORT_SCENE.atlasModules(level, nextView).some((item) => item.id === S.selection.id)) S.selection = null;
    render();
  }



  // The Atlas consumes Core assignments and receipts; geometry and selection are presentation.
  function atlasLevel() {
    return ATLAS.levels.find((level) => level.parent_id === (S.path.at(-1)?.id || null))
      || ATLAS.levels[0];
  }


  const atlasOwnerPalette = ["var(--line-strong)", "var(--ink-subtle)", "var(--ink-muted)", "var(--line-strong)", "var(--ink-subtle)", "var(--ink-muted)"];
  const atlasComponentIds = ATLAS.components.map((item) => item.id).sort();
  function atlasOwnerColor(componentId) {
    const index = atlasComponentIds.indexOf(componentId);
    return index < 0 ? null : { index, color: atlasOwnerPalette[index % atlasOwnerPalette.length] };
  }
  function atlasReferences(item, field) {
    return (item[field] || []).map((index) => ATLAS.reference_ids[index]);
  }
  function atlasFindings(level) {
    const ids = new Set((level.finding_ids || []).map((reference) => Number.isInteger(reference)
      ? ATLAS.findings[reference]?.id : reference));
    return (ATLAS.findings || []).filter((finding) => ids.has(finding.id));
  }
  function atlasBalanceLine(title, balance) {
    return `${title}: ${balance?.declared ?? "UNKNOWN"} declared · ${balance?.used ?? "UNKNOWN"} used · ${balance?.allowed_unused ?? "UNKNOWN"} allowed but unused · ${balance?.undeclared ?? "UNKNOWN"} undeclared`;
  }
  function atlasDeviationHref(deviation) {
    const query = new URLSearchParams(location.search);
    query.delete("scope");
    if (deviation.level_id) query.set("component", deviation.level_id);
    else query.delete("component");
    query.set("view", "diff");
    query.set("selected", deviation.source_id);
    query.delete("content");
    return `${location.pathname}?${query}`;
  }
  function atlasBalanceMarkup(level) {
    if (S.view !== "diff") return "";
    const own = new Set(level.deviation_ids || []);
    const deviations = (ATLAS.deviations || []).filter((item) => own.has(item.id));
    return `<section class="atlas-balance"><p>${esc(atlasBalanceLine("This level", level.balance))}</p>
      <p>${esc(atlasBalanceLine("Whole system", ATLAS.balance))}</p>
      ${deviations.length ? `<ul class="plain">${deviations.map((item) => {
        const source = REPORT_SCENE.atlasComponent(item.source_id)?.label || item.source_id;
        const target = REPORT_SCENE.atlasComponent(item.target_id)?.label || item.target_id;
        const kind = item.kind === "allowed_unused" ? "Allowed but unused" : "Undeclared";
        return `<li><a href="${esc(atlasDeviationHref(item))}">${esc(kind)} · ${esc(source)} → ${esc(target)}</a></li>`;
      }).join("")}</ul>` : ""}</section>`;
  }
  function atlasInsideDeviations(componentId) {
    const ids = new Set();
    for (const level of ATLAS.levels) {
      if (level.parent_id === componentId || REPORT_SCENE.componentRoute(level.parent_id).some((item) => item.id === componentId)) {
        (level.deviation_ids || []).forEach((id) => ids.add(id));
      }
    }
    return (ATLAS.deviations || []).filter((row) => ids.has(row.id));
  }
  function atlasComponentFindingCount(componentId) {
    const level = ATLAS.levels.find((item) => item.parent_id === componentId);
    return level ? atlasFindings(level).length : 0;
  }
  function atlasGlobalSymbolsComplete() {
    if (typeof ATLAS.symbols_complete === "boolean") return ATLAS.symbols_complete;
    return ATLAS.modules.length > 0 && ATLAS.modules.every((module) =>
      module.symbol_coverage.length > 0 && module.symbol_coverage.every((item) => item.status === "complete"));
  }
  function atlasFindingsMarkup(level, modules) {
    const findings = atlasFindings(level), groups = new Map();
    findings.forEach((finding) => {
      for (const rule of finding.rule_ids.length ? finding.rule_ids : [""]) {
        const key = `${rule}\0${finding.kind}`;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(finding);
      }
    });
    return `<details class="atlas-findings" open><summary>Findings · ${findings.length}</summary>
      ${[...groups].map(([key, entries]) => {
      const [rule, kind] = key.split("\0");
      const sharedRemedy = entries.length > 1 && entries.every((finding) =>
        finding.remedy && finding.remedy === entries[0].remedy) ? entries[0].remedy : null;
      return `<details id="atlas-rule-${esc(rule)}" class="atlas-finding-group"><summary>${esc(rule)} · ${esc(kind)} · ${REPORT_SCENE.countLabel(entries.length, "finding")}</summary>${sharedRemedy ? `<p class="atlas-shared-remedy">${esc(sharedRemedy)}</p>` : ""}<ul class="plain">${entries.map((finding) => {
      const recorded = ATLAS.modules.find((item) => item.path === finding.path);
      const assignment = level.modules.find((item) => item.id === recorded?.id);
      const module = modules.find((item) => item.path === finding.path)
        || (recorded ? { ...recorded, ...assignment } : null);
      const source = finding.path ? `${finding.path}${finding.line ? `:${finding.line}` : ""}` : "Source not recorded";
        const href = module ? atlasModuleHref(module.id) : null;
        const remedy = finding.remedy && finding.remedy !== sharedRemedy
          ? `<p class="atlas-finding-remedy">${esc(finding.remedy)}</p>` : "";
        const nested = finding.nested_annotation
          ? `<p class="atlas-nested-annotation">Nested type: <code>${esc(finding.nested_annotation)}</code></p>` : "";
        return `<li id="atlas-finding-${esc(finding.id)}-${esc(encodeURIComponent(rule))}"><strong>${esc(finding.title)}</strong>${nested}<p>${href ? `<a href="${esc(href)}" data-atlas-module-route="${esc(module.id)}">${esc(source)}</a>` : `<code>${esc(source)}</code>`}</p>${remedy}</li>`;
      }).join("")}</ul></details>`;
      }).join("") || "<p>No recorded findings at this level.</p>"}</details>`;
  }
  function openAtlasFindingHash(requestedId = null) {
    let id = requestedId;
    if (id === null) {
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { pendingAtlasFindingHash = null; return; }
    }
    if (openBoundaryPermissionHash(id)) return;
    if (!id.startsWith("atlas-rule-") && !id.startsWith("atlas-finding-") && !id.startsWith("atlas-assessment-")) {
      pendingAtlasFindingHash = null;
      return;
    }
    const target = document.getElementById(id);
    if (!target) { pendingAtlasFindingHash = id; return; }
    pendingAtlasFindingHash = null;
    if (inspector.contains(target)) setTargetDetails(true);
    if (root.querySelector(".flow-explore")?.contains(target))
      root.dispatchEvent(new CustomEvent("archkeel:findings"));
    for (let ancestor = target; ancestor; ancestor = ancestor.parentElement) {
      if (ancestor instanceof HTMLDetailsElement) ancestor.open = true;
    }
    requestAnimationFrame(() => target.scrollIntoView());
  }
  window.addEventListener("hashchange", () => openAtlasFindingHash());
  root.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const url = new URL(link.href, location.href);
    if (url.pathname === location.pathname && url.search === location.search && url.hash === location.hash)
      openAtlasFindingHash();
  });
  function atlasComponentNavigation(id) {
    const component = id && REPORT_SCENE.atlasComponent(id);
    return component && ATLAS.components.some((item) => item.parent_id === id)
      ? { scope: id, selected: null }
      : component ? { scope: component.parent_id, selected: id } : { scope: null, selected: null };
  }
  function atlasComponentHref(id) {
    const query = new URLSearchParams(location.search);
    for (const key of ["component", "scope", "module", "selected", "cell", "content"]) query.delete(key);
    const navigation = atlasComponentNavigation(id);
    if (navigation.scope) query.set("scope", navigation.scope);
    if (navigation.selected) query.set("selected", navigation.selected);
    query.set("view", S.view);
    return `${location.pathname}?${query}`;
  }
  function atlasComponentLink(id, label) {
    return `<a href="${esc(atlasComponentHref(id))}" data-atlas-component-route="${esc(id || "")}">${esc(label)}</a>`;
  }
  function followAtlasComponentRoute(event) {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest("[data-atlas-component-route]");
    if (!link) return;
    const id = link.dataset.atlasComponentRoute || null;
    if (id && !REPORT_SCENE.atlasComponent(id)) return;
    event.preventDefault();
    const navigation = atlasComponentNavigation(id);
    dispatch({ type: "openLevel", id: navigation.scope });
    if (navigation.selected) dispatch({ type: "select", id: navigation.selected });
  }
  (root.closest("main") || root).addEventListener("click", followAtlasComponentRoute);
  document.addEventListener("DOMContentLoaded", () => syncRoute(true), { once: true });
  function atlasRuleScopeHref(level, ruleId) {
    const query = new URLSearchParams(location.search);
    query.delete("component");
    if (level.parent_id) query.set("scope", level.parent_id);
    else query.delete("scope");
    query.set("view", S.view);
    return `${location.pathname}?${query}#atlas-rule-${encodeURIComponent(ruleId)}`;
  }
  // A finding count in plain words, from the phrase that the core page gives each rule kind.
  function atlasPlainFindings(ruleId, count) {
    const rule = (ATLAS.rule_assessments || []).find((item) => item.id === ruleId);
    const phrase = rule && (count === 1 ? rule.plain_one : rule.plain_many);
    return phrase ? `${count} ${phrase}` : REPORT_SCENE.countLabel(count, "finding");
  }
  // The anchor of the first violation block of a rule, on the page.
  function atlasFindingHref(findings, ruleId) {
    const found = findings.find((finding) => finding.rule_ids.includes(ruleId));
    return found ? `#${found.id}` : "";
  }
  function atlasRuleAssessmentMarkup(level, component = null) {
    const assessments = ATLAS.rule_assessments || [];
    const scopedLevel = component ? ATLAS.levels.find((item) => item.parent_id === component.id) : level;
    const findings = scopedLevel ? atlasFindings(scopedLevel) : [];
    const failureGroups = new Map();
    findings.forEach((finding) => finding.rule_ids.forEach((rule) =>
      failureGroups.set(rule, (failureGroups.get(rule) || 0) + 1)));
    const statuses = ["PASS", "FAIL", "UNKNOWN"].map((status) =>
      `${status} ${assessments.filter((item) => item.status === status).length}`).join(" · ");
    const notChecked = ATLAS.declared_rules === "NOT CHECKED" ? " · NOT CHECKED" : "";
    const recordedChecks = `<section class="atlas-scoped-findings"><h3>Recorded checks${component ? ` · ${esc(component.label)}` : ""}</h3>
      <p>${findings.length ? `${REPORT_SCENE.countLabel(findings.length, "finding")} recorded in this scope.` : (component ? "No violation in this component." : "No violation in this scope.")}</p>
      ${failureGroups.size ? `<ul class="plain">${[...failureGroups].map(([ruleId, count]) =>
      `<li><a href="${esc(atlasFindingHref(findings, ruleId) || atlasRuleScopeHref(scopedLevel || level, ruleId))}">${esc(atlasPlainFindings(ruleId, count))}</a> <small class="muted">(${esc(ruleId)})</small></li>`).join("")}</ul>` : ""}</section>`;
    if (component) return recordedChecks;
    return `${recordedChecks}<details class="atlas-rule-assessments"><summary>Rules · whole run ${esc(ATLAS.declared_rules || "NOT CHECKED")} · ${statuses}${notChecked}</summary>
      <p>Whole-run rule assessments; local findings are scoped separately above. Each UNKNOWN keeps its rule, reason and scope.</p>
      ${assessments.length ? `<ul class="plain">${assessments.map((item) => {
      const localCount = failureGroups.get(item.id) || 0;
      const rule = localCount
        ? `<a href="${esc(atlasRuleScopeHref(scopedLevel || level, item.id))}">${esc(item.id)}</a>`
        : `<code>${esc(item.id)}</code>`;
      const evidence = item.evidence.length
        ? `<ul>${item.evidence.map((entry) => `<li>${esc(entry.kind)} · ${esc(entry.title)} · ${esc(entry.subjects.join(", "))}${entry.subject_count > entry.subjects.length ? ` (+${entry.subject_count - entry.subjects.length} subjects in audit)` : ""}${entry.reason ? ` · ${esc(entry.reason)}` : ""} · <a href="${esc(ATLAS.architecture_href)}">record ${esc(entry.id)} in architecture JSON</a></li>`).join("")}</ul>`
        : "";
      const scope = atlasComponentLink(item.scope_id, item.scope);
      const affected = item.component_ids.map((id) => {
        const component = ATLAS.components.find((entry) => entry.id === id);
        return atlasComponentLink(id, component?.scope || id);
      }).join(", ");
      const uncertainEvidence = item.status === "UNKNOWN" || item.undecided > 0
        ? `<p>Affected scope: ${scope}</p>${affected ? `<p>Affected components: ${affected}</p>` : ""}
          <p>Recorded uncertainty evidence: ${item.evidence.length} of ${item.evidence_count} records.</p>${evidence}
          ${item.uncertainty_actions.length ? `<ul>${item.uncertainty_actions.map((action) =>
            `<li data-uncertainty-cause="${esc(action.cause)}" data-architect-actionable="${action.architect_actionable ?? "unknown"}"><strong>${esc(action.cause.replaceAll("_", " "))}</strong> · ${action.architect_actionable === true ? "Architect decision required" : action.architect_actionable === false ? "Evidence or analysis action required" : "Architect actionability not established"}: ${esc(action.next_action)}</li>`).join("")}</ul>`
            : "<p>Next action: inspect the recorded reason and affected scope. No cause was established for this uncertainty.</p>"}
          <p><a href="${esc(ATLAS.architecture_href)}">Complete evidence in architecture JSON</a></p>` : "";
      return `<li id="atlas-assessment-${esc(item.id)}" tabindex="-1"><strong class="atlas-rule-status ${esc(item.status.toLowerCase())}">${esc(item.status)}</strong> · ${rule} (${esc(item.kind)}) · ${scope} · ${esc(item.reason)}`
        + `${item.count ? ` · ${REPORT_SCENE.countLabel(item.count, "recorded result")}` : ""}`
        + `${item.undecided ? ` · ${REPORT_SCENE.countLabel(item.undecided, "undecided result")}` : ""}`
        + `${uncertainEvidence}</li>`;
      }).join("")}</ul>` : "<p>Rule assessments were not recorded.</p>"}</details>`;
  }
  // The analysis limits that the frame names, each with its reason. The verdict of the run is on the
  // card; a sheet repeats none of it.
  function atlasEvidenceMarkup() {
    if (!ATLAS.unknowns.length) return "";
    return `<section class="atlas-evidence"><h3>Analysis limits</h3>
      <ul class="plain">${ATLAS.unknowns.map((item) => `<li>${REPORT_SCENE.countLabel(item.count, "analysis limit")} · ${esc(item.reason)}</li>`).join("")}</ul></section>`;
  }
  // Issue 1471: a module has no page of its own. A module route is a URL of this page: the level that
  // shows the module in its module view, with the module selected.
  function atlasModuleLevel(id) {
    const current = atlasLevel();
    if (root.dataset.content === "modules" && REPORT_SCENE.atlasModules(current, S.view).some((item) => item.id === id))
      return current;
    let found = null, depth = -1;
    for (const level of ATLAS.levels) {
      const levelDepth = REPORT_SCENE.componentRoute(level.parent_id).length;
      if (levelDepth > depth && REPORT_SCENE.atlasModules(level, S.view).some((item) => item.id === id)) {
        found = level; depth = levelDepth;
      }
    }
    return found;
  }

  function atlasLevelQuery(parentId) {
    const query = new URLSearchParams(location.search);
    for (const key of ["component", "scope", "module", "selected", "cell", "content"]) query.delete(key);
    if (parentId) query.set("scope", parentId);
    query.set("view", S.view);
    return query;
  }

  function atlasLevelHref(parentId) { return `${location.pathname}?${atlasLevelQuery(parentId)}`; }

  function atlasModuleHref(id) {
    const level = atlasModuleLevel(id) || atlasLevel();
    const query = atlasLevelQuery(level.parent_id);
    if (atlasHasChoice(level)) query.set("content", "modules");
    query.set("selected", id);
    return `${location.pathname}?${query}`;
  }

  function atlasModuleShown(id) {
    return root.dataset.content === "modules" && atlasModuleLevel(id) === atlasLevel();
  }

  function atlasModuleLink(module, label) {
    return `<a href="${esc(atlasModuleHref(module.id))}" data-atlas-module-route="${esc(module.id)}">${esc(label)}</a>`;
  }

  function openAtlasModule(id) {
    const level = atlasModuleLevel(id);
    if (!level) return;
    const moved = level !== atlasLevel() || root.dataset.content !== "modules";
    if (!moved) { selectArchitectureSubject("node", id); return; }
    navigate();
    S.path = REPORT_SCENE.componentRoute(level.parent_id).map((item) => ({ id: item.id, origin: "observed" }));
    S.content = "modules";
    S.selection = { type: "node", id };
    S.module = S.view !== "target" && REPORT_SCENE.atlasModuleById(id) ? id : null;
    S.cell = null; S.hint = null; S.allHints = false;
    setTargetDetails(true);
    positions = Object.create(null); render(); fit();
  }

  function followAtlasModuleRoute(event) {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const module = event.target.closest("[data-atlas-module-route]");
    const level = event.target.closest("[data-atlas-level-route]");
    if (!module && !level) return;
    event.preventDefault();
    dispatch(module ? { type: "openModule", id: module.dataset.atlasModuleRoute }
      : { type: "openLevel", id: level.dataset.atlasLevelRoute });
  }
  (root.closest("main") || root).addEventListener("click", followAtlasModuleRoute);

  function openAtlasComponent(id, content = null) {
    if (!ATLAS.levels.some((level) => level.parent_id === id)) return;
    navigate();
    S.path = REPORT_SCENE.componentRoute(id).map((item) => ({ id: item.id, origin: "observed" }));
    S.content = content;
    S.selection = null;
    S.module = null; S.cell = null; S.hint = null; S.allHints = false;
    positions = Object.create(null); render(); fit(); focusCurrentLevel();
  }

  function atlasLayoutKey(scene, level) {
    const layoutEdges = scene.componentOverview ? scene.layoutEdges : scene.edges;
    return `atlas:${JSON.stringify([
      scene.componentOverview ? "components" : S.view,
      level.parent_id,
      scene.nodes.map((node) => [
        node.id, node.module?.component_id, node.label, cardHeight(node.id),
      ]),
      layoutEdges.map((edge) => [edge.layoutId || edge.id, edge.source, edge.target, edge.label]),
    ])}`;
  }

  async function requestLayout(key, generation, create) {
    let promise = layoutPromises.get(key);
    if (!promise) {
      promise = create();
      layoutPromises.set(key, promise);
    }
    try {
      const result = await promise;
      return layoutPromises.get(key) === promise && generation === layoutGeneration ? result : null;
    } catch (error) {
      if (layoutPromises.get(key) === promise) layoutPromises.delete(key);
      if (generation !== layoutGeneration) return null;
      throw error;
    }
  }

  function finishLayout() {
    layoutPending = false;
    if (!pendingLayoutFit) return;
    const overview = pendingLayoutFitOverview, whole = pendingLayoutFitWhole;
    pendingLayoutFit = false;
    pendingLayoutFitOverview = false;
    pendingLayoutFitWhole = false;
    fit(overview, { whole });
  }

  async function layoutAtlasScene(scene, level) {
    const layoutEdges = scene.componentOverview ? scene.layoutEdges : scene.edges;
    const result = await REPORT_LAYOUT.layoutAtlas({
      componentOverview: scene.componentOverview,
      parentId: level.parent_id,
      nodes: scene.nodes.map((node) => ({ id: node.id, ownerId: node.module?.place_id || node.module?.component_id,
        label: node.module?.path || node.module?.name || node.label })),
      edges: layoutEdges.map((edge) => ({ id: edge.id, layoutId: edge.layoutId || edge.id,
        source: edge.source, target: edge.target, label: edge.label || "" })),
      components: ATLAS.components.map((component) => ({
        id: component.id, parentId: component.parent_id, label: component.label,
      })),
      cardWidth: CARD.w,
      cardHeights: Object.fromEntries(scene.nodes.map((node) => [node.id, cardHeight(node.id)])),
    });
    const positions = Object.create(null), frames = [], routesById = new Map();
    for (const node of scene.nodes) {
      const id = `${scene.componentOverview ? "component" : "module"}:${node.id}`;
      positions[node.id] = result.positions[id];
    }
    for (const [layoutId, frame] of Object.entries(result.frames)) {
      const id = layoutId.slice("component:".length);
      const component = REPORT_SCENE.atlasComponent(id);
      const parent = frame.parentId?.startsWith("component:")
        ? frame.parentId.slice("component:".length) : null;
      frames.push({ id, parent,
        kind: "component", label: component?.label || id,
        scope: component?.label || id,
        tooltip: `${component?.label || id}: ${(component?.responsibilities || []).join(" ")}`,
        bounds: { left: frame.left, right: frame.right, top: frame.top,
          bottom: frame.bottom, header: 50 },
      });
    }
    for (const edge of layoutEdges) {
      const layoutId = edge.layoutId || edge.id;
      const elkId = scene.componentOverview ? `edge:${layoutId}` : `edge:${edge.id}`;
      const route = result.routes.get(elkId);
      const label = result.labels[`label:${layoutId}`];
      if (scene.componentOverview && !label) {
        throw new Error(`ELK did not place the label for relationship ${layoutId}.`);
      }
      routesById.set(layoutId, { ...route,
        lx: label ? label.x + label.width / 2 : route.mid[0],
        ly: label ? label.y + label.height - 2 : route.ly,
      });
    }
    return { positions, frames, routesById, bounds: result.bounds };
  }

  function moduleInventoryMarkup(inventories) {
    const plannedFiles = inventories.flatMap((item) => item.modules);
    return `<section class="flow-module-inventory">${plannedFiles.length ? `<details><summary>Module inventory · ${REPORT_SCENE.countLabel(plannedFiles.length, "planned file")}</summary>
      <p>File intent does not define classes, methods, imports or calls.</p>${S.view !== "target" ? "<p>Observed file presence is separate from a Core verdict.</p>" : ""}<ul class="plain">${plannedFiles.map((item) => {
        const actual = S.view === "target" ? null : DATA.observed?.entities.find((entity) => entity.kind === "module" && entity.presence === "defined" && entity.file_path === item.path);
        const findings = (S.view === "target" ? [] : DATA.findings || []).filter((finding) => finding.subjects.includes(item.path));
        return `<li data-file-intent="${esc(item.path)}"><code>${esc(item.path)}</code><p>${esc(item.responsibility)}</p>${S.view !== "target" ? `<p>${DATA.observed ? actual ? `Observed module: ${esc(actual.qualified_name)}` : "Not in the observed file inventory." : "Source facts are unavailable."}</p>` : ""}${findings.length ? findingMarkup(findings) : ""}</li>`;
      }).join("")}</ul></details>` : `<h3>Module inventory</h3><p>${inventories.length ? "Explicitly empty" : "Not declared"}</p>`}
      <p>${[...new Set(inventories.flatMap((item) => item.provenance))].map(esc).join(" · ")}</p></section>`;
  }

  // The symbols of a module: the count when the run has one, else the limit in plain words, once.
  // The coverage record states it (`unavailable` and its reason); nothing is said when it states none.
  function atlasSymbolsLine(module) {
    if (module.symbols != null) return REPORT_SCENE.countLabel(module.symbols, "observed symbol");
    const limit = (module.symbol_coverage || []).find((item) => item.status === "unavailable");
    if (!limit) return "";
    const reason = (limit.reason || "").replace(/\.$/, "");
    return `Symbols: not counted${reason ? ` (${esc(reason.charAt(0).toLowerCase() + reason.slice(1))})` : ""}`;
  }
  // What a box is: a layer or a group of components, or a component.
  function atlasBoxKind(component) {
    if (component.directory) return "Directory";
    // A box that holds one component is that component, whatever its id says.
    if (component.groups === null || component.groups === undefined || component.groups === 1) return "Component";
    return component.layer_rank !== null && component.layer_rank !== undefined ? "Layer" : "Group";
  }
  // The public names of a box, grouped by module with short names and a count. The module paths lose
  // the part that they all share. Many names fold behind the line that counts them.
  function atlasProvidesMarkup(names) {
    if (!names || !names.length) return "";
    const byModule = new Map();
    for (const name of names) {
      const at = name.lastIndexOf(":");
      const module = at < 0 ? "" : name.slice(0, at), short = at < 0 ? name : name.slice(at + 1);
      if (!byModule.has(module)) byModule.set(module, []);
      byModule.get(module).push(short);
    }
    const paths = [...byModule.keys()].map((path) => path.split("."));
    let shared = 0;
    while (paths.length && paths.every((parts) => parts.length > shared + 1 && parts[shared] === paths[0][shared])) shared += 1;
    const rows = [...byModule].map(([module, shorts]) => {
      const label = module ? module.split(".").slice(shared).join(".") || module : "";
      // Every name is listed: the fold above the list opens to the whole interface.
      return `<li>${label ? `<strong>${esc(label)}</strong> (${shorts.length}): ` : ""}${shorts.map(esc).join(", ")}</li>`;
    }).join("");
    const title = `Provides · ${REPORT_SCENE.countLabel(names.length, "name")}${byModule.size > 1 ? ` in ${REPORT_SCENE.countLabel(byModule.size, "module")}` : ""}`;
    return names.length > 6 ? `<details class="atlas-provides"><summary>${title}</summary><ul class="plain">${rows}</ul></details>`
      : `<h3>${title}</h3><ul class="plain">${rows}</ul>`;
  }
  // What a component owns, as one short line: one package or module is named, many are counted.
  function atlasOwnsMarkup(path) {
    const parts = path.split(", ");
    return parts.length === 1 ? `<p class="muted">Owns <code>${esc(parts[0])}</code></p>`
      : `<details class="atlas-owns"><summary>owns ${REPORT_SCENE.countLabel(parts.length, "package or module", "packages and modules")}</summary><p>${parts.map(esc).join(", ")}</p></details>`;
  }
  // The declared dependencies of a component: one line each, the way through folded behind a count.
  function atlasRequiresMarkup(component) {
    if (!component.requires.length) return "";
    const rows = component.requires.map((edge) => {
      const through = edge.through.length > 2
        ? `<details><summary>through ${REPORT_SCENE.countLabel(edge.through.length, "path")}</summary><p>${edge.through.map(esc).join(", ")}</p></details>`
        : edge.through.length ? `<p class="muted">through ${edge.through.map(esc).join(", ")}</p>` : "";
      const seen = S.view !== "target" ? ` · ${REPORT_SCENE.countLabel(edge.observed_imports, "observed import")}` : "";
      return `<li><strong>${esc(REPORT_SCENE.atlasComponent(edge.target_id)?.label || edge.target_id)}</strong>${seen}<p>${esc(edge.rationale)}</p>${through}</li>`;
    }).join("");
    return `<details class="atlas-requires"><summary>Requires · ${REPORT_SCENE.countLabel(component.requires.length, "declared dependency", "declared dependencies")}</summary><ul class="plain">${rows}</ul></details>`;
  }
  function atlasSheet(level, scene = renderedScene) {
    const component = REPORT_SCENE.atlasComponent(S.selection?.id || level.parent_id);
    const inventory = S.view === "target" ? moduleInventoryMarkup(ATLAS.module_inventories
      .filter((item) => item.component_id === (component?.id || null))) : "";
    const entries = (items) => items ? items.map((item) => `<li>${esc(item)}</li>`).join("") : "";
    const list = (title, items) => items && items.length ? `<h3>${title}</h3><ul class="plain">${entries(items)}</ul>` : "";
    const link = (href, label) => `<a href="${esc(href)}">${esc(label)}</a>`;
    if (S.view !== "target" && S.cell !== null) {
      const cell = ATLAS.cells[S.cell];
      const source = REPORT_SCENE.atlasModuleById(cell.source_id), target = REPORT_SCENE.atlasModuleById(cell.target_id);
      inspectorContent.innerHTML = `<div class="kicker">Observed import cell</div><h2>${esc(source.name)} → ${esc(target.name)}</h2>
        <p>${atlasModuleLink(source, `Show ${source.name}`)}</p>
        <p>${cell.import_sites ?? "UNKNOWN"} import sites · Core finding status: <strong>${esc(cell.status)}</strong></p>
        <p>Permission: <strong>${esc(cell.permission)}</strong></p><p>${esc(cell.permission_reason)}</p>
        ${list("Recorded reasons", cell.reasons)}${list("Finding IDs", atlasReferences(cell, "finding_ids"))}
        ${list("Evidence IDs", atlasReferences(cell, "evidence_ids"))}`;
      return;
    }
    if (S.view !== "target" && S.module) {
      const module = REPORT_SCENE.atlasModuleById(S.module);
      const assignment = ATLAS.assignments.find((item) => item.id === module.id);
      const owner = REPORT_SCENE.atlasComponent(assignment?.component_id);
      const grouped = (direction) => {
        const rows = ATLAS.cells.filter((cell) => cell[direction === "in" ? "target_id" : "source_id"] === module.id);
        const groups = new Map();
        let outside = 0;
        for (const cell of rows) {
          const id = cell[direction === "in" ? "source_id" : "target_id"];
          const other = REPORT_SCENE.atlasModuleById(id);
          const binding = ATLAS.assignments.find((item) => item.id === id);
          const known = REPORT_SCENE.atlasComponent(binding?.component_id)?.label;
          // A module that no component owns is no component: it is counted apart.
          if (!known) outside += 1;
          const name = known || "Outside the contract";
          if (!groups.has(name)) groups.set(name, []);
          groups.get(name).push(`<li>${esc(other.name)} · ${REPORT_SCENE.countLabel(cell.import_sites, "site")}</li>`);
        }
        if (!rows.length) return "";
        // Many modules fold behind the line that counts them, as the provided names do.
        const components = groups.size - (outside ? 1 : 0);
        const counted = [components ? `${REPORT_SCENE.countLabel(rows.length - outside, "module")} in ${REPORT_SCENE.countLabel(components, "component")}` : "",
          outside ? `${REPORT_SCENE.countLabel(outside, "module")} outside the contract` : ""].filter(Boolean).join(" · ");
        const title = `${direction === "in" ? "Imported by" : "Imports"} · ${counted}`;
        const body = [...groups].map(([name, items]) => `<h4>${esc(name)}</h4><ul class="plain">${items.join("")}</ul>`).join("");
        return rows.length > 4 ? `<details class="atlas-imports"><summary>${title}</summary>${body}</details>` : `<h3>${title}</h3>${body}`;
      };
      inspectorContent.innerHTML = `<div class="kicker">Observed module · counts over the observed source scope</div>
        <h2>${esc(module.name)}</h2>${atlasModuleShown(module.id) ? "" : `<p>${atlasModuleLink(module, "Show in the module view")}</p>`}${module.path ? `<p><code>${esc(module.path)}</code></p>` : ""}
        <p>${atlasSymbolsLine(module)}</p>
        <p>fan-in ${module.fan_in ?? "UNKNOWN"} · fan-out ${module.fan_out ?? "UNKNOWN"}</p>
        <h3>Owner</h3><p>${esc(owner?.label || "UNKNOWN")} · ${esc(assignment?.ownership_reason || "No assignment receipt")}</p>
        ${owner ? list("Responsibility", owner.responsibilities) + list("Not responsible for", owner.not_responsible_for) : list("Candidate owners", assignment?.candidate_ids || [])}
        ${grouped("in")}${grouped("out")}
        ${boundaryPermissionMarkup(module.id, new Set([module.id]))}`;
      return;
    }
    if (S.view === "target") {
      const module = REPORT_SCENE.atlasModules(level, S.view).find((item) => item.id === S.selection?.id);
      if (module) {
        inspectorContent.innerHTML = `<div class="kicker">Declared module</div><h2>${esc(module.name)}</h2>
          ${atlasModuleShown(module.id) ? "" : `<p>${atlasModuleLink(module, "Show in the module view")}</p>`}<p><code>${esc(module.path || "File path not declared")}</code></p>
          <p>${REPORT_SCENE.countLabel(module.declarations, "direct declared definition")}</p>${list("Responsibility", module.responsibilities)}${list("Provenance", module.provenance)}
          ${boundaryPermissionMarkup(module.id, new Set([module.id]))}
          ${list("Authored module relationships", scene.edges.filter((edge) => edge.source === module.id || edge.target === module.id)
            .map((edge) => `${edge.id} · ${edge.relationshipKind}: ${edge.source} → ${edge.target} · ${edge.declaration.evidence_ids.join(", ")}`))}`;
        return;
      }
    }
    if (!component) {
      inspectorContent.innerHTML = `<div class="kicker">Fact sheet${S.view === "target" ? " · Declared intent" : ""}</div><h2>${esc(ATLAS.repository)}</h2>
        <p>${S.view === "target" ? "Select a component or declared module." : "Select a component, module, import cell or question."}</p>
        ${inventory}${boundaryPermissionMarkup()}
        ${S.view === "target" ? "" : `${atlasRuleAssessmentMarkup(level)}${atlasEvidenceMarkup()}`}
        <p>${link(ATLAS.architecture_href, "Complete audit JSON")}</p>`;
      return;
    }
    const componentLevel = ATLAS.levels.find((item) => item.parent_id === component.id);
    const moduleCount = componentLevel ? REPORT_SCENE.atlasModules(componentLevel, S.view).length : 0;
    const usedBy = component.used_by.map((item) => `${esc(REPORT_SCENE.atlasComponent(item.component_id)?.label || item.component_id)} (${item.import_sites})`).join(", ");
    inspectorContent.innerHTML = `<div class="kicker">${atlasBoxKind(component)} fact sheet · ${S.view === "target" ? "Declared intent" : "Core facts"}</div>
      ${boundaryPermissionMarkup(component.id)}<h2>${esc(component.label)}</h2><p><button type="button" class="flow-fit" data-browse-component>${moduleCount ? `Browse ${REPORT_SCENE.countLabel(moduleCount, "module")}` : `Browse ${esc(component.label)}`}</button>${component.layer ? ` <span class="muted">layer ${esc(component.layer)}</span>` : ""}</p>${list(component.directory ? "About" : "Responsibility", component.responsibilities)}
      ${list("Not responsible for", component.not_responsible_for)}${atlasProvidesMarkup(component.public)}
      ${list("Planned interface", component.planned)}${atlasRequiresMarkup(component)}
      ${S.view === "target" ? "" : atlasRuleAssessmentMarkup(level, component)}${S.view !== "target" ? `<h3>In this run</h3><p>${REPORT_SCENE.countLabel(component.observed_modules, "module")}${component.observed_symbols == null ? "" : ` · ${REPORT_SCENE.countLabel(component.observed_symbols, "observed symbol")}`} · ${esc(component.status)} · ${esc(component.reason)}</p>${usedBy ? `<h3>Used by</h3><p>${usedBy}</p>` : ""}` : ""}
      <p class="muted">${component.directory ? `The report made this box from the module paths; ${esc(REPORT_SCENE.atlasComponent(component.parent_id)?.label || component.parent_id)} owns the modules in the contract.` : component.decided_by === "report" ? "Grouped by the report (structure): the report made this box to keep the level readable. Each component inside keeps its own decisions in the contract." : `Decided by ${esc(component.decided_by || "the contract")}`}</p>${S.view === "target" || !component.path || component.directory ? "" : atlasOwnsMarkup(component.path)}
      ${component.provenance.length ? `<details><summary>Reasons · ${REPORT_SCENE.countLabel(component.provenance.length, "document")}</summary><ul class="plain">${component.provenance.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></details>` : ""}${inventory}
      ${S.view === "target" && componentLevel ? `<p><a href="${esc(atlasLevelHref(component.id))}" data-atlas-level-route="${esc(component.id)}">Open declared component details</a></p>` : ""}`;
    inspectorContent.querySelector("[data-browse-component]").onclick = () =>
      dispatch({ type: "openLevel", id: component.id, content: "modules" });
  }

  function atlasQuestion(hint) {
    const subject = hint.kind === "hub" ? ["importing module", "importing modules"]
      : hint.kind === "heavy" ? ["symbol", "symbols"]
        : hint.kind === "no_owner" ? ["authenticated owner", "authenticated owners"]
          : ["import site", "import sites"];
    return `Repository: ${ATLAS.repository}\nCommit: ${ATLAS.source.git_head}\nSource digest: ${ATLAS.source.source_digest}\nModules: ${hint.module_ids.map((id) => REPORT_SCENE.atlasModuleById(id).name).join(", ")}\nObserved count: ${REPORT_SCENE.countLabel(hint.count, ...subject)}\nEvidence IDs: ${atlasReferences(hint, "evidence_ids").join(", ")}\nRelationship IDs: ${atlasReferences(hint, "relationship_ids").join(", ")}\nQuestion: ${hint.question}\nProvisional hint, not a verdict.`;
  }

  async function copyAtlasQuestion(hint, button) {
    const text = atlasQuestion(hint);
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied";
    } catch {
      const area = document.createElement("textarea");
      area.readOnly = true; area.value = text;
      area.setAttribute("aria-label", "Question and recorded evidence");
      button.parentElement.appendChild(area); area.focus(); area.select();
    }
  }

  function atlasHasChoice(level, view = S.view) { return Boolean(level.component_ids.length && REPORT_SCENE.atlasModules(level, view).length); }

  function atlasModuleList(level) {
    const modules = REPORT_SCENE.atlasModules(level, S.view);
    return `<section class="atlas-module-list"><h3>${S.view === "target" ? "Declared" : "Observed"} ${REPORT_SCENE.countLabel(modules.length, "module")}</h3><ul class="plain">
      ${modules.map((module) => `<li>${atlasModuleLink(module, module.path?.split("/").at(-1) || module.name)}
        · ${S.view === "target" ? REPORT_SCENE.countLabel(module.declarations, "direct declared definition") : REPORT_SCENE.countLabel(module.symbols, "observed symbol")}
        <p><code>${esc(module.path || module.name)}</code>${module.path ? "" : " · File path not declared"}</p></li>`).join("")}</ul></section>`;
  }

  function atlasContentPane(level) {
    const modules = REPORT_SCENE.atlasModules(level, S.view), choice = root.querySelector(".atlas-content-choice");
    const content = level.component_ids.length ? S.content === "modules" && modules.length ? "modules" : "components" : "modules";
    root.dataset.content = content;
    choice.hidden = !atlasHasChoice(level);
    choice.innerHTML = [["components", level.component_ids.length], ["modules", modules.length]].map(([kind, count]) =>
      `<button type="button" class="flow-fit" data-content="${kind}" aria-pressed="${content === kind}">${kind === "components" ? "Components" : "Modules"} (${count})</button>`).join("");
    choice.querySelectorAll("button").forEach((button) => button.onclick = () =>
      dispatch({ type: "setContent", content: button.dataset.content }));
    return content;
  }

  let atlasExploreModules = [];

  function setAtlasExploreOpen(open) {
    S.explore = open;
    if (open) atlasMatrix(atlasLevel(), atlasExploreModules);
  }

  function atlasExplore(level) {
    const explore = root.querySelector(".flow-explore");
    if (S.view === "target") {
      explore.innerHTML = `${atlasFindingsMarkup(level, REPORT_SCENE.atlasModules(level, S.view))}<h3>Explore</h3><p>Target shows declarations only. Switch to As-Is or Diff for observed modules and question candidates.</p>`;
      return;
    }
    const componentOrder = new Map(renderedScene.nodes.slice().sort((a, b) => positions[a.id].y - positions[b.id].y
      || positions[a.id].x - positions[b.id].x).map((node, index) => [node.id, index]));
    const modules = atlasExploreModules = REPORT_SCENE.atlasModules(level, S.view)
      .sort((a, b) => (componentOrder.get(a.component_id) ?? componentOrder.size) - (componentOrder.get(b.component_id) ?? componentOrder.size)
        || (a.rank ?? Infinity) - (b.rank ?? Infinity) || a.name.localeCompare(b.name));
    const shown = S.allHints ? level.questions : level.questions.slice(0, 5);
    const titles = { used_elsewhere: "Used elsewhere", hub: "Hub", heavy: "Heavy", no_owner: "No owner" };
    explore.innerHTML = `${atlasBalanceMarkup(level)}${atlasFindingsMarkup(level, modules)}
      <div class="atlas-explore-heading"><h3>Worth a look</h3><span>${REPORT_SCENE.countLabel(modules.length, "module")} · ${REPORT_SCENE.countLabel(level.cells.length, "module dependency", "module dependencies")}</span></div>
      <p>Deterministic question candidates from Core, not verdicts. Thresholds remain provisional.</p>
      <ul class="atlas-questions">${shown.map((index) => {
        const hint = ATLAS.questions[index];
        const subject = hint.kind === "hub" ? ["importing module", "importing modules"]
          : hint.kind === "heavy" ? ["observed symbol", "observed symbols"]
            : hint.kind === "no_owner" ? ["authenticated owner", "authenticated owners"]
              : ["observed import site", "observed import sites"];
        return `<li><span class="atlas-chip">${titles[hint.kind]}</span> ${REPORT_SCENE.countLabel(hint.count, ...subject)}
          <p>${hint.module_ids.map((id) => `<code>${esc(REPORT_SCENE.atlasModuleById(id).name)}</code>`).join(", ")}</p><p>${esc(hint.question)}</p>
          <button type="button" data-show-question="${index}">Show in matrix</button> <button type="button" data-copy-question="${index}">Copy as question</button></li>`;
      }).join("") || '<li>No question candidates at this level.</li>'}</ul>
      ${level.questions.length > 5 ? `<button type="button" data-all-questions>${S.allHints ? "Show fewer" : `Show all ${level.questions.length} questions`}</button>` : ""}
      <h3>Module matrix</h3><p>Row imports column. Neutral: Core PASS · Red: Core FAIL · Amber: Core UNKNOWN.
      Module permission is never inferred from a declared requires edge.</p>
      <p class="atlas-coverage">${esc(level.import_status)}: ${esc(level.import_reason)}</p>
      <div class="flow-matrix" role="region" aria-label="Module import matrix" tabindex="0"></div>
      <details class="atlas-module-list"><summary>Modules and UML · ${modules.length}</summary></details>`;
    if (!level.questions.length) {
      explore.querySelector(".atlas-explore-heading").remove();
      explore.querySelector(".atlas-questions").previousElementSibling.remove();
      explore.querySelector(".atlas-questions").remove();
    }
    const list = explore.querySelector("details.atlas-module-list");
    list.addEventListener("toggle", () => {
      if (list.open && !list.querySelector("section")) list.insertAdjacentHTML("beforeend", atlasModuleList(level));
    });
    explore.querySelectorAll("[data-copy-question]").forEach((button) => button.onclick = () => copyAtlasQuestion(ATLAS.questions[Number(button.dataset.copyQuestion)], button));
    explore.querySelectorAll("[data-show-question]").forEach((button) => button.onclick = () =>
      dispatch({ type: "showHint", index: Number(button.dataset.showQuestion) }));
    const more = explore.querySelector("[data-all-questions]");
    if (more) more.onclick = () => dispatch({ type: "toggleAllHints" });
    if (S.explore) atlasMatrix(level, modules);
  }

  function atlasMatrixGeometry(matrix, modules) {
    const n = modules.length, requestedSize = Math.max(2.4, Math.min(16, 720 / Math.max(1, n)));
    const size = requestedSize >= 9 && requestedSize < 12 ? 12 : requestedSize;
    const groups = [];
    for (let start = 0; start < n;) {
      let end = start + 1;
      while (end < n && modules[end].component_id === modules[start].component_id) end++;
      groups.push({ start, end, name: modules[start].component_id
        ? `${REPORT_SCENE.atlasComponent(modules[start].component_id)?.label || "Component"} · inside` : "Root" });
      start = end;
    }
    const probe = el("text", { class: "matrix-group-label" });
    matrix.appendChild(probe);
    measureText.font = getComputedStyle(probe).font;
    const labelWidth = Math.max(120, ...groups.map((group, index) => {
      const range = `${group.start + 1}–${group.end}`;
      return Math.max(
        measureText.measureText(`${index + 1}. ${group.name} · columns ${range}`).width,
        measureText.measureText(`${index + 1}. ${group.name} · rows ${range}`).width,
      );
    }));
    probe.setAttribute("class", "matrix-label");
    measureText.font = getComputedStyle(probe).font;
    const margin = size < 9 ? 54 : Math.max(154, ...modules.map((module) =>
      measureText.measureText(module.name.split(".").slice(-2).join(".")).width + 12));
    probe.remove();
    const bandHeight = 28 + groups.length * 14, gridTop = margin + bandHeight;
    matrix.setAttribute("width", String(Math.max(margin + n * size + 12, margin + labelWidth * 2 + 20)));
    matrix.setAttribute("height", String(gridTop + n * size + 12));
    return { size, groups, margin, labelWidth, gridTop };
  }

  function atlasMatrix(level, modules) {
    const region = root.querySelector(".flow-matrix");
    if (!region || region.firstChild) return;
    const matrix = el("svg", {
      role: "img", "aria-label": `${REPORT_SCENE.countLabel(modules.length, "module")}. A row imports a column.` });
    region.appendChild(matrix);
    const { size, groups, margin, labelWidth, gridTop } = atlasMatrixGeometry(matrix, modules);
    const indexes = new Map(modules.map((module, index) => [module.id, index]));
    const columnHeading = el("text", { class: "matrix-axis-heading", x: String(margin), y: "14" });
    columnHeading.textContent = "Column groups · left to right"; matrix.appendChild(columnHeading);
    const rowHeading = el("text", { class: "matrix-axis-heading", x: String(margin + labelWidth + 20), y: "14" });
    rowHeading.textContent = "Row groups · top to bottom"; matrix.appendChild(rowHeading);
    groups.forEach((group, index) => {
      const y = String(28 + index * 14), range = `${group.start + 1}–${group.end}`;
      for (const [axis, x] of [["column", margin], ["row", margin + labelWidth + 20]]) {
        const label = el("text", { class: "matrix-group-label", "data-axis": axis, x: String(x), y });
        label.textContent = `${index + 1}. ${group.name} · ${axis === "column" ? "columns" : "rows"} ${range}`;
        matrix.appendChild(label);
      }
      matrix.appendChild(el("rect", { class: "matrix-block",
        x: String(margin + group.start * size), y: String(gridTop + group.start * size),
        width: String((group.end - group.start) * size), height: String((group.end - group.start) * size) }));
    });
    modules.forEach((module, index) => {
      if (size < 9) return;
      for (const column of [false, true]) {
        const label = el("text", { class: "matrix-label", "data-module": module.id, tabindex: "0", role: "button",
          x: String(column ? margin + (index + .5) * size : margin - 6),
          y: String(column ? gridTop - 6 : gridTop + (index + .7) * size), "text-anchor": column ? "start" : "end",
          ...(column ? { transform: `rotate(-90 ${margin + (index + .5) * size} ${gridTop - 6})` } : {}) });
        label.textContent = module.name.split(".").slice(-2).join(".");
        label.appendChild(el("title")); label.lastChild.textContent = module.name;
        matrix.appendChild(label);
      }
    });
    for (const index of level.cells) {
      const cell = ATLAS.cells[index], row = indexes.get(cell.source_id), column = indexes.get(cell.target_id);
      if (row === undefined || column === undefined) continue;
      const state = cell.status === "FAIL" ? "fail" : cell.status === "UNKNOWN" ? "unknown" : "pass";
      const rect = el("rect", { class: `matrix-cell ${state}${S.view === "diff" && cell.status !== "FAIL" ? " quiet" : ""}`,
        "data-cell": String(index), tabindex: "0", role: "button",
        "aria-label": `${modules[row].name} imports ${modules[column].name}: ${REPORT_SCENE.countLabel(cell.import_sites, "site")}; Core ${cell.status}; permission ${cell.permission}`,
        x: String(margin + column * size), y: String(gridTop + row * size), width: String(Math.max(2.4, size - 1)), height: String(Math.max(2.4, size - 1)) });
      const title = el("title"); title.textContent = rect.getAttribute("aria-label"); rect.appendChild(title); matrix.appendChild(rect);
    }
    const choose = (event) => {
      const cell = event.target.closest("[data-cell]"), module = event.target.closest("[data-module]");
      if (!cell && !module) return;
      dispatch({ type: "selectMatrix", cell: cell ? Number(cell.dataset.cell) : null, module: module?.dataset.module || null });
    };
    matrix.addEventListener("click", choose);
    matrix.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); choose(event); } });
    atlasHighlightQuestion();
  }

  function atlasHighlightQuestion() {
    const highlighted = new Set(S.hint === null ? [] : ATLAS.questions[S.hint].module_ids);
    root.querySelectorAll(".matrix-cell").forEach((rect) => {
      const cell = ATLAS.cells[Number(rect.dataset.cell)];
      rect.classList.toggle("highlighted", highlighted.has(cell.source_id) || highlighted.has(cell.target_id));
    });
  }

  async function renderAtlas() {
    const level = atlasLevel(), content = atlasContentPane(level);
    const scene = content === "modules" ? REPORT_SCENE.atlasModuleScene(level, S.view) : REPORT_SCENE.atlasScene(level, S.view);
    atlasSheet(level, scene);
    root.dataset.view = S.view; root.dataset.umlGraph = "true"; root.dataset.componentOverview = "true";
    flowHeading.textContent = level.parent_id ? `Architecture map · ${REPORT_SCENE.atlasComponent(level.parent_id)?.label || level.parent_id}` : "Architecture map";
    canvas.hidden = !scene.nodes.length; alternative.hidden = Boolean(scene.nodes.length);
    if (!scene.nodes.length) {
      alternative.innerHTML = `<div class="flow-scope-notice"><h3>${S.view === "target" ? "No declared subcomponents. No declared modules recorded." : "No observed content recorded."}</h3><p>${S.view === "target" ? "Declared facts remain in the Inspector; observed modules are not Target declarations." : "No native module content is recorded for this scope."}</p>${S.view === "target" ? '<button type="button" class="flow-fit" data-show-as-is>Show As-Is modules</button>' : ""}</div>`;
      const asIs = alternative.querySelector("[data-show-as-is]");
      if (asIs) asIs.onclick = () => dispatch({ type: "setView", view: "diagram" });
    }
    viewButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.flowView === S.view)));
    elementKindControl.hidden = true; focusInput.closest("label").hidden = true; violationFocus.hidden = true;
    fitButton.hidden = true; memberPreviewsButton.hidden = true; unassignedCodeButton.hidden = true;
    filters.hidden = true;
    architectureNavigation();
    const agentComponents = scene.nodes.filter((node) => node.component?.decided_by === "agent").length;
    const agentEdges = scene.declared.filter((edge) => edge.decided_by === "agent").length;
    const observed = scene.edges.filter((edge) => !edge.declaration);
    const boundary = scene.moduleOverview && scene.boundaryEdges
      ? ` · ${REPORT_SCENE.countLabel(scene.boundaryEdges, "cross-scope relationship")} not drawn at this level` : "";
    root.querySelector(".atlas-summary").textContent = scene.grouped
      ? `Current level: ${REPORT_SCENE.countLabel(scene.grouped.modules, S.view === "target" ? "declared module" : "observed module")} in ${REPORT_SCENE.countLabel(scene.nodes.length, "box", "boxes")}: more than ${scene.grouped.limit} modules are grouped by component or directory · open a box to see its modules · Search finds one module`
      : scene.moduleOverview
      ? S.view === "target" ? `Current level: ${REPORT_SCENE.countLabel(scene.nodes.length, "declared module")} · ${REPORT_SCENE.countLabel(scene.edges.length, "authored module relationship")}${boundary}`
        : `Current level: ${REPORT_SCENE.countLabel(scene.nodes.length, "observed module")} · ${REPORT_SCENE.countLabel(observed.length, "local dependency", "local dependencies")} · ${REPORT_SCENE.countLabel(observed.every((edge) => edge.import_sites !== null) ? observed.reduce((sum, edge) => sum + edge.import_sites, 0) : null, "import site")}${boundary}`
      : S.view === "target"
      ? `Current level: ${REPORT_SCENE.countLabel(scene.nodes.length, "component")} · ${REPORT_SCENE.countLabel(scene.declared.length, "dependency", "dependencies")} · agent-authored contract entries (authorship only): ${agentComponents}/${scene.nodes.length} components, ${agentEdges}/${scene.declared.length} dependencies`
      : `Current level: ${REPORT_SCENE.countLabel(observed.length, "observed dependency", "observed dependencies")} · ${REPORT_SCENE.countLabel(observed.every((edge) => edge.import_sites !== null) ? observed.reduce((sum, edge) => sum + edge.import_sites, 0) : null, "import")} · ${S.view === "diff" ? "recorded failures highlighted; unproven permission UNKNOWN" : "source facts"}`;
    cardHeights.clear(); scene.nodes.forEach((node) => {
      cardHeights.set(node.id, scene.moduleOverview ? 144 : 178);
    }); CARD.h = Math.max(144, ...cardHeights.values());
    const generation = layoutGeneration;
    if (!scene.nodes.length) {
      layoutPending = false;
      renderAtlasScene(level, content, scene, {
        positions: {}, frames: [], routesById: new Map(),
      });
      root.dataset.layoutState = "ready";
      finishLayout();
      return;
    }
    const key = atlasLayoutKey(scene, level);
    layoutPending = true;
    root.dataset.layoutState = "pending";
    frameLayer.textContent = ""; nodeLayer.textContent = ""; edgeLayer.textContent = ""; chipLayer.textContent = "";
    legend.textContent = scene.moduleOverview
      ? "Arranging authored ownership and module relationships…"
      : "Arranging component relationships…";
    try {
      const result = await requestLayout(key, generation, () => layoutAtlasScene(scene, level));
      if (!result) return;
      const expectedContent = scene.moduleOverview ? "modules" : "components";
      if (root.dataset.content !== expectedContent) return;
      renderAtlasScene(level, content, scene, result);
      root.dataset.layoutState = "ready";
      finishLayout();
    } catch (error) {
      if (generation !== layoutGeneration) return;
      finishLayout();
      root.dataset.layoutState = "error";
      canvas.hidden = true; alternative.hidden = false;
      alternative.innerHTML = `<div class="flow-scope-notice" role="alert"><h3>Architecture layout unavailable</h3><p>${esc(error.message || "The authenticated relationships could not be arranged.")}</p><p>Next step: use Search to open one module or component, or reload the page to arrange the diagram again.</p></div>`;
    }
  }

  // Selection and hover share one rule: the focus, its neighbours and their edges stay lit.
  function atlasEmphasize(preview = null) {
    const scene = renderedScene;
    if (!scene) return;
    const focus = preview || (S.selection?.type === "node" ? { type: "node", id: S.selection.id } : null);
    const nodes = new Set(), edges = new Set();
    if (focus?.type === "node") {
      nodes.add(focus.id);
      for (const edge of scene.edges) if (edge.source === focus.id || edge.target === focus.id) {
        edges.add(edge.id); nodes.add(edge.source); nodes.add(edge.target);
      }
    } else if (focus?.type === "edge") {
      edges.add(focus.id); nodes.add(focus.source); nodes.add(focus.target);
    }
    nodeLayer.querySelectorAll("[data-uml-id]").forEach((node) => {
      node.classList.toggle("dim", Boolean(focus && !nodes.has(node.dataset.umlId)));
      node.classList.toggle("preview", Boolean(preview?.type === "node" && preview.id === node.dataset.umlId));
    });
    edgeLayer.querySelectorAll("[data-uml-id]").forEach((edge) => {
      edge.classList.toggle("dim", Boolean(focus && !edges.has(edge.dataset.umlId)));
      edge.classList.toggle("related", Boolean(preview && edges.has(edge.dataset.umlId)));
    });
  }

  function renderAtlasScene(level, content, scene, layout) {
    if (scene.moduleOverview) {
      scene.frames = layout.frames;
    }
    scene.layoutRoutes = scene.edges.map((edge) => {
      const route = layout.routesById.get(edge.layoutId || edge.id);
      if (!route) throw new Error(`ELK did not route active relationship ${edge.id}.`);
      return { ...route, edge };
    });
    const connected = new Set(scene.edges.flatMap((edge) => [edge.source, edge.target]));
    const isolated = new Set(scene.nodes.filter((node) => !connected.has(node.id)).map((node) => node.id));
    positions = layout.positions;
    renderUmlScene(scene, {
      frame(group, frame) {
        if (frame.kind !== "component") return;
        const ownerColor = atlasOwnerColor(frame.id);
        if (ownerColor) {
          group.dataset.ownerColor = String(ownerColor.index);
          group.style.setProperty("--atlas-owner-color", ownerColor.color);
        }
        const open = () => dispatch({ type: "openLevel", id: frame.id, content: "modules" });
        group.addEventListener("click", (event) => {
          if (!event.target.closest(".target-frame-header-hit")) return;
          event.stopPropagation(); open();
        });
        group.addEventListener("keydown", (event) => {
          if (["Enter", " "].includes(event.key)) { event.preventDefault(); open(); }
        });
      },
      node(group, node) {
        const ownerColor = atlasOwnerColor(node.module?.component_id || node.id);
        if (ownerColor) {
          group.dataset.ownerColor = String(ownerColor.index);
          group.style.setProperty("--atlas-owner-color", ownerColor.color);
        }
        if (scene.moduleOverview) group.dataset.moduleInventory = String(isolated.has(node.id));
        group.classList.toggle("selected", S.selection?.type === "node" && S.selection.id === node.id);
        group.setAttribute("aria-pressed", String(S.selection?.type === "node" && S.selection.id === node.id));
        const meta = group.querySelector(".meta");
        const lines = [...meta.children];
        const allowed = Math.max(1, Math.floor((112 - Number(meta.getAttribute("y"))) / 14) + 1);
        if (lines.length > allowed) {
          lines.slice(allowed).forEach((line) => line.remove());
          const last = lines[allowed - 1];
          last.textContent = last.textContent.trimEnd().slice(0, -1) + "…";
        }
        if (S.view !== "target") {
          if (node.component) group.dataset.assessmentStatus = node.component.status;
          const weight = el("text", { class: "atlas-weight", x: "16", y: "129" });
          const inventoryComplete = atlasGlobalSymbolsComplete();
          weight.textContent = node.module ? (node.module.symbols == null ? "" : `${node.module.symbols} observed symbols`)
            : `${node.component.observed_modules} mod${node.component.observed_symbols == null ? "" : ` · ${node.component.observed_symbols} sym`}${node.component.symbols_complete === inventoryComplete ? "" : node.component.symbols_complete ? " · complete" : " · partial"}`;
          group.appendChild(weight);
        }
        if (S.view !== "target" && !scene.moduleOverview && node.component) {
          const findingCount = atlasComponentFindingCount(node.id);
          const chipText = window.ArchkeelReportScene.deviationChipText(node.component.status, atlasInsideDeviations(node.id));
          // Each chip, and each part of the deviation chip, has its own line inside the box (issue 1694).
          const lines = [
            ...(findingCount ? [["atlas-finding-chip", `${REPORT_SCENE.countLabel(findingCount, "finding")} inside`]] : []),
            ...(chipText ? chipText.split(" · ") : []).flatMap((part) => wrapText(part, CARD.w - 32, `11px ${sansFontFamily}`))
              .map((line) => ["atlas-deviation-chip", line])];
          const top = Math.max(143, Math.min(151, 179 - lines.length * 14));
          lines.forEach(([kind, line], index) => {
            const chip = el("text", { class: kind, x: "16", y: String(top + index * 14) });
            chip.textContent = line;
            group.appendChild(chip);
          });
        }
        group.addEventListener("click", (event) => { event.stopPropagation(); dispatch({ type: "select", id: node.id }); });
        group.addEventListener("dblclick", (event) => { event.preventDefault(); dispatch({ type: "open", id: node.id }); });
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter") { event.preventDefault(); dispatch({ type: "open", id: node.id }); }
          if (event.key === " ") { event.preventDefault(); dispatch({ type: "select", id: node.id }); }
        });
        group.addEventListener("pointerenter", (event) => {
          if (event.pointerType === "mouse") atlasEmphasize({ type: "node", id: node.id });
        });
        group.addEventListener("pointerleave", () => atlasEmphasize());
        group.addEventListener("focus", () => atlasEmphasize({ type: "node", id: node.id }));
        group.addEventListener("blur", () => atlasEmphasize());
      },
      edge(drawn, route) {
        drawn.line.style.strokeDasharray = route.edge.unused ? "6 4" : "none";
        drawn.line.style.markerEnd = `url(#flow-arrow-${route.edge.state === "violation" ? "violation" : "declared"})`;
        if (route.edge.import_sites) drawn.line.style.strokeWidth = String(1.2 + Math.log10(route.edge.import_sites) * 1.4);
        if (!scene.moduleOverview) {
          const label = el("text", { class: "atlas-edge-label", x: String(route.lx), y: String(route.ly), "text-anchor": "middle" });
          label.textContent = route.edge.label; drawn.group.appendChild(label);
        }
        const choose = () => dispatch(route.edge.cell !== undefined
          ? { type: "selectEdgeCell", cell: route.edge.cell } : { type: "selectEdgeSource", id: route.edge.source });
        drawn.hit.addEventListener("click", choose);
        drawn.hit.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); choose(); } });
        const edgeFocus = { type: "edge", id: route.edge.id, source: route.edge.source, target: route.edge.target };
        drawn.group.addEventListener("pointerenter", () => atlasEmphasize(edgeFocus));
        drawn.group.addEventListener("pointerleave", () => atlasEmphasize());
      },
    }, scene.layoutRoutes);
    atlasEmphasize();
    legend.textContent = scene.grouped
      ? `${REPORT_SCENE.countLabel(scene.grouped.modules, "module")} grouped by component or directory · Enter or a double click opens a box and shows its modules`
      : scene.moduleOverview ? S.view === "target"
      ? "Target modules · authored relationships · Enter or a click selects a module and shows its facts"
      : "Observed modules · local directed relationships · Enter or a click selects a module and shows its facts"
      : S.view === "target" ? "Target edges · requires = declared permission · full rationale in tooltip and Details"
        : S.view === "diff" ? "Diff edges · red: undeclared · solid: permitted and used · dashed: allowed but unused"
          : "Directed dependencies · shared positions across views · counts are observed import sites";
    atlasExplore(level); atlasSheet(level);
    if (pendingAtlasFindingHash || location.hash) openAtlasFindingHash(pendingAtlasFindingHash);
    updateOpenSelected(); sizeDiagram();
  }

  function render() {
    layoutGeneration += 1;
    layoutPending = false;
    pendingLayoutFit = false;
    pendingLayoutFitOverview = false;
    pendingLayoutFitWhole = false;
    syncRoute();
    if (routeNotice) renderRouteNotice();
    else renderAtlas();
  }


  toolbar.hidden = false;
  root.querySelector(".flow-views").hidden = false;
  violationFocus.hidden = false;
  violationFocus.classList.add("flow-graph-filter");
  violationsOnly.addEventListener("change", () => { positions = Object.create(null); render(); fit(); });
  viewButtons.forEach((button) => button.addEventListener("click", () => dispatch({ type: "setView", view: button.dataset.flowView })));
  backButton.addEventListener("click", () => dispatch({ type: "up" }));
  openSelectedButton.addEventListener("click", () => {
    if (S.selection?.type === "node") { dispatch({ type: "open", id: S.selection.id }); fit(); }
  });
  focusInput.addEventListener("change", () => { focusLabel = focusInput.value || null; positions = Object.create(null); render(); fit(); });
  elementKindInput.addEventListener("change", () => { elementKind = elementKindInput.value || null; focusLabel = null; positions = Object.create(null); render(); fit(); });
  legend.addEventListener("click", (event) => {
    const button = event.target.closest("[data-relationship-kind]");
    if (!button) return;
    relationshipKind = button.dataset.relationshipKind || null;
    positions = Object.create(null);
    render(); fit();
  });
  const resetFlow = () => {
    focusLabel = null; relationshipKind = null; elementKind = null; S.selection = null; positions = Object.create(null);
    showExternalSymbols = false; showAllModuleElements = false;
    violationsOnly.checked = false;
    transform.k = 1;
    render(); fit();
  };
  resetFiltersButton.remove();
  zoom100Button.addEventListener("click", resetFlow);
  fitButton.addEventListener("click", () => { positions = Object.create(null); render(); fit(); });
  overviewButton.addEventListener("click", () => fit(true, { whole: true }));
  zoomOutButton.addEventListener("click", () => zoomBy(1 / 1.2));
  zoomInButton.addEventListener("click", () => zoomBy(1.2));
  let spaceHeld = false;
  const editing = (target) => target.closest?.("input, textarea, select, [contenteditable='true']");
  window.addEventListener("keydown", (event) => {
    if (event.code !== "Space" || event.defaultPrevented || editing(event.target)
      || event.target.closest?.("button, a, summary, [role='button']")
      || !canvas.contains(event.target) && !canvas.matches(":hover")) return;
    event.preventDefault();
    spaceHeld = true;
    svg.classList.add("space-pan");
  });
  window.addEventListener("keyup", (event) => {
    if (event.code !== "Space") return;
    spaceHeld = false;
    svg.classList.remove("space-pan");
  });
  window.addEventListener("blur", () => {
    spaceHeld = false;
    svg.classList.remove("space-pan");
  });
  canvas.addEventListener("wheel", (event) => {
    // Plain wheel and two-finger scroll keep panning natively; pinch arrives as a ctrlKey wheel.
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    zoomAt(Math.exp(-event.deltaY * 0.0015), event.clientX, event.clientY);
  }, { passive: false });
  svg.addEventListener("pointerdown", (event) => {
    const panButton = event.button === 0 || event.button === 1;
    if (!event.isPrimary || !panButton || (!spaceHeld && event.button === 0 && event.target.closest(".node, .hit"))) return;
    capturePointer(svg, event);
    panState = { x: event.clientX, y: event.clientY, offset: { ...panOffset } };
    svg.classList.add("panning");
    event.preventDefault();
  });
  svg.addEventListener("pointermove", (event) => {
    if (panState) {
      panOffset = {
        x: panState.offset.x + (event.clientX - panState.x) / transform.k,
        y: panState.offset.y + (event.clientY - panState.y) / transform.k,
      };
      viewport.setAttribute("transform", `translate(${panOffset.x} ${panOffset.y})`);
    }
  });
  svg.addEventListener("pointerup", (event) => {
    if (panState) {
      skipSvgClick = Math.hypot(event.clientX - panState.x, event.clientY - panState.y) > 3;
      panState = null;
      svg.classList.remove("panning");
    }
  });
  svg.addEventListener("pointercancel", () => {
    panState = null;
    svg.classList.remove("panning");
  });
  svg.addEventListener("click", (event) => {
    if (skipSvgClick) { skipSvgClick = false; return; }
    if (!event.target.closest(".node, .hit")) dispatch({ type: "clearSelection" });
  });
  fullscreenButton.addEventListener("click", async () => {
    if (root.dataset.expanded) {
      restoreExpansion();
      return;
    }
    expansionRestore = {
      focus: document.activeElement,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      bodyOverflow: document.body.style.overflow,
      inert: [...document.querySelectorAll("main > *")].filter((element) =>
        !element.contains(root)).map((element) => [element, element.inert]),
    };
    try {
      if (root.requestFullscreen) {
        await root.requestFullscreen();
        return;
      }
    } catch {
      // A browser or embedding policy can deny the direct request.
    }
    document.body.style.overflow = "hidden";
    root.dataset.expanded = S.expanded = "fallback";
    syncExpansionInert();
    sizeDiagram();
    root.setAttribute("aria-modal", "true");
    root.setAttribute("role", "dialog");
    fullscreenButton.textContent = "Back to report";
    fullscreenButton.setAttribute("aria-label", "Back to report");
    expandStatus.textContent = "Expanded in this window";
    expandStatus.hidden = false;
    fullscreenButton.focus({ preventScroll: true });
  });
  document.addEventListener("fullscreenchange", updateFullscreenState);
  root.addEventListener("keydown", (event) => {
    // E3: Escape is one ladder (report-canvas.js): overlay, popover, drawer, expanded, selection.
    if (event.defaultPrevented || event.target.closest("dialog")) return;
    if (event.key === "Tab" && root.dataset.expanded === "fallback") {
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


  detailsToggle.addEventListener("click", () => dispatch({ type: "setDetails", open: !S.details }));
  if (NAV) {
    setTargetDetails(true);
    readRoute();
    document.querySelector(".theme-toggle").addEventListener("click", () =>
      dispatch({ type: "setTheme", theme: document.documentElement.dataset.theme !== "light" ? "light" : "dark" }));
    window.addEventListener("popstate", () => dispatch({ type: "restoreRoute" }));
  }
  // The presentation choices of report-canvas.js. dispatch stores them in S; their effects stay there.
  const PRESENTATION = ["perspective", "pinnedTag", "drawer", "overlay", "pop"];

  // E3: up one level is derived from S.path; the level that you leave is selected in its parent.
  function atlasUp() {
    if (!S.path.length) return;
    navigate();
    const child = S.path.at(-1);
    S.path = S.path.slice(0, -1);
    S.selection = { type: "node", id: child.id }; S.module = null; S.cell = null; S.hint = null; S.content = null;
    routeNotice = null; positions = Object.create(null); render(); fit();
  }

  // A new layout of the same state: the size of the page changed.
  function relayout() { positions = Object.create(null); render(); fit(); }

  function goToDepth(depth) {
    navigate();
    S.path = S.path.slice(0, depth); S.selection = null; routeNotice = null;
    S.module = null; S.cell = null; S.hint = null; S.content = null; positions = Object.create(null); render(); fit();
  }

  function selectAtlasSheet(level, changes) {
    Object.assign(S, changes);
    setTargetDetails(true); syncRoute(); atlasSheet(level);
  }

  // AD-734: the one door of a user action. Each case is one transition of S and draws its result.
  function dispatch(action) {
    historyMode = "replace";
    try { transition(action); } finally { historyMode = "replace"; publishState(); }
  }

  function transition(action) {
    switch (action.type) {
      case "openLevel": openAtlasComponent(action.id ?? null, action.content ?? null); break;
      case "goToDepth": goToDepth(action.depth); break;
      case "open": openArchitectureEntity(action.id); break;
      case "openModule": openAtlasModule(action.id); break;
      case "up": atlasUp(); break;
      case "relayout": relayout(); break;
      case "collapse": restoreExpansion(); break;
      case "setView": switchArchitectureView(action.view); break;
      case "setContent": navigate(); S.content = action.content; render(); fit(); break;
      case "select": selectArchitectureSubject(action.kind || "node", action.id); break;
      case "clearSelection": S.selection = null; S.module = null; S.cell = null; S.hint = null; render(); break;
      case "selectMatrix": selectAtlasSheet(atlasLevel(), { cell: action.cell, module: action.module }); break;
      case "selectEdgeCell": selectAtlasSheet(atlasLevel(), { cell: action.cell, module: null, selection: null }); break;
      case "selectEdgeSource":
        selectAtlasSheet(atlasLevel(), { selection: { type: "node", id: action.id }, module: null, cell: null }); break;
      case "showHint": {
        const level = atlasLevel();
        selectAtlasSheet(level, { hint: action.index, module: ATLAS.questions[action.index].module_ids[0], cell: null });
        root.dispatchEvent(new CustomEvent("archkeel:findings"));
        atlasHighlightQuestion();
        root.querySelector(".flow-explore .flow-matrix")?.focus();
        break;
      }
      case "toggleAllHints": S.allHints = !S.allHints; atlasExplore(atlasLevel()); break;
      case "setDetails": setTargetDetails(action.open); render(); fit(); break;
      case "setExplore": setAtlasExploreOpen(action.open); break;
      case "setTheme": setTheme(action.theme === "light" ? "light" : "dark"); break;
      case "openRule": {
        openAtlasComponent(action.rule.scope_id || null);
        setTargetDetails(true);
        const id = `atlas-assessment-${action.rule.id}`;
        if (["file:", "http:", "https:"].includes(location.protocol)) location.hash = encodeURIComponent(id);
        openAtlasFindingHash(id);
        break;
      }
      case "restoreRoute": S.pinnedTag = null; routeReady = false; readRoute(); render(); fit(); routeReady = true; syncRoute(true); break;
      case "present":
        for (const key of PRESENTATION) if (Object.hasOwn(action, key)) S[key] = action[key];
        // The perspective and the drawer are in the URL; an overlay, a popover and a pinned tag are not.
        if (Object.hasOwn(action, "perspective") || Object.hasOwn(action, "drawer")) syncRoute();
        break;
      default: throw new Error(`Unknown Explorer action: ${action.type}`);
    }
  }

  // Seam for presentation controllers (report-canvas.js). No verdict logic crosses it.
  window.ArchkeelFlow = {
    root, svg, canvas, nodeLayer, edgeLayer, atlas: ATLAS, reportScene: REPORT_SCENE,
    // S is read only here: a change goes through dispatch.
    S, dispatch,
    selectElement: (id) => dispatch({ type: "select", id }),
    fit, zoomBy, zoomAt, syncExpansionInert, emphasize: atlasEmphasize,
    setMaxFitScale: (value) => { maxFitScale = value; },
    openComponent: (id) => dispatch({ type: "openLevel", id }),
    selectComponent: (id) => {
      dispatch({ type: "openLevel", id: REPORT_SCENE.atlasComponent(id).parent_id });
      dispatch({ type: "select", id });
    },
    moduleHref: (module) => atlasModuleHref(module.id),
    openModule: (id) => dispatch({ type: "openModule", id }),
    setExploreOpen: (open) => dispatch({ type: "setExplore", open }),
    openRule: (rule) => dispatch({ type: "openRule", rule }),
    state: () => ({ ...stateView(), viewMode: S.view, scene: renderedScene, zoom: transform.k }),
    toQuery, fromQuery,
  };
  render();
  openAtlasFindingHash();
  routeReady = true; syncRoute(true);
  fit();
  window.addEventListener("resize", () => {
    if (root.dataset.content === "modules") { render(); fit(); }
    else sizeDiagram();
  });

})();
