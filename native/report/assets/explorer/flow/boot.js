  // The data of the page, the one view state S (AD-734), the DOM handles and the controls of the Explorer.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  const root = document.getElementById("flow");
  const dataNode = document.getElementById("flow-data");
  // A thrown text stops the Explorer and names no global (a part cannot return at its top).
  if (!root || !dataNode) throw "The page has no Explorer markup or data.";
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
    throw "Unsupported architecture report schema.";
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
