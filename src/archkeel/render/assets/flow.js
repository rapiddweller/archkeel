"use strict";
// AD-10: component flow view. No external library, no CDN, no Math.random/Date/timers -
// every run over the same embedded data produces the same layout.
(function () {
  const root = document.getElementById("flow");
  const dataNode = document.getElementById("flow-data");
  if (!root || !dataNode) return;
  const flowHeading = document.getElementById("flow-heading");
  flowHeading.tabIndex = -1;
  const DATA = JSON.parse(dataNode.textContent);
  const CARD = { w: 200, h: 92 };
  const GAP = 34;
  const ROW_GAP = 150;
  const PER_ROW = 6;
  const FRAME_HEADER_HEIGHT = 53;
  const TARGET_RESIDUAL_GAP = 20;
  let TARGET_FRAME_HEADER_ALLOWANCE = FRAME_HEADER_HEIGHT;
  const LANE_GAP = 11;

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
  const legend = root.querySelector(".flow-legend");
  const thresholdInput = root.querySelector(".flow-threshold");
  const thresholdValue = root.querySelector(".flow-threshold-value");
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
  const backButton = root.querySelector(".flow-back");
  const breadcrumb = root.querySelector(".flow-breadcrumb");
  const viewButtons = root.querySelectorAll("[data-flow-view]");
  const alternative = root.querySelector(".flow-alternative");
  const responsibilities = root.querySelector(".flow-responsibilities");
  const openSelectedButton = root.querySelector(".flow-open-selected");
  const fullscreenButton = root.querySelector(".flow-fullscreen");
  const expandStatus = root.querySelector(".flow-expand-status");
  const responsibilitySearch = root.querySelector(".flow-responsibility-search");
  const responsibilityList = root.querySelector(".flow-responsibility-list");
  const responsibilityCount = root.querySelector(".flow-responsibility-count");
  const selectedResponsibility = root.querySelector(".flow-selected-responsibility");
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

  function setTargetDetails(open) {
    targetDetailsOpen = open;
    root.dataset.detailsOpen = String(open);
    detailsToggle.setAttribute("aria-expanded", String(open));
    detailsToggle.setAttribute("aria-label", "Details " + (open ? "open" : "closed"));
    inspector.hidden = !open;
  }

  detailsToggle.addEventListener("click", () => {
    setTargetDetails(!targetDetailsOpen);
  });

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

  const sansFontFamily = getComputedStyle(document.documentElement)
    .getPropertyValue("--ck-font-sans").replace(/\s+/g, " ").trim();
  const monoFontFamily = getComputedStyle(document.documentElement)
    .getPropertyValue("--ck-font-mono").replace(/\s+/g, " ").trim();
  const measureCanvas = document.createElement("canvas");
  const measureText = measureCanvas.getContext("2d");
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

  function appendWrappedText(parent, value, attrs, maxWidth, font, lineHeight) {
    const lines = wrapText(value, maxWidth, font);
    const text = el("text", attrs);
    lines.forEach((line, index) => {
      const tspan = el("tspan", {
        x: attrs.x,
        dy: index ? String(lineHeight) : "0",
      });
      tspan.textContent = line;
      text.appendChild(tspan);
    });
    parent.appendChild(text);
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
  let lastPointerTap = null;

  // AD-24: inner edges stay observed unless the declared inside rules decide their pair.
  // AD-24a: a module opens the same way, one level deeper, in the same {components, edges}
  // shape, because layout, ranking, routing and the inspector all consume that shape.
  function insideScope() {
    if (!opened || opened.module) return null;
    const component = componentByLabel.get(opened.component);
    if (!component) return null;
    if (!opened.inside) {
      return component.inside
        ? { inside: component.inside, card: component, declared: true }
        : { card: component, declared: false };
    }
    let inside = component.inside;
    let card = (inside?.components || []).find((item) => item.label === opened.inside);
    if (!card) return null;
    if (!(opened.insidePath || []).length) {
      // A physical path below an inside card belongs to its module tree, even when the card
      // also declares a same-named inside level.
      if ((opened.path || []).length) return { card, declared: false };
      if (card.inside) return { inside: card.inside, card, declared: true };
      return opened.physicalInsideCard ? { card, declared: false } : null;
    }
    for (const [index, label] of opened.insidePath.entries()) {
      inside = card.inside;
      card = (inside?.components || []).find((item) => item.label === label);
      if (!card) return null;
      if (card.inside) continue;
      return opened.physicalInsideCard && index === opened.insidePath.length - 1
        ? { card, declared: false }
        : null;
    }
    if ((opened.path || []).length) return { card, declared: false };
    return card.inside ? { inside: card.inside, card, declared: true } : null;
  }

  function fullLevel() {
    if (!opened) {
      return { components: rootCards, edges: DATA.edges };
    }
    if (opened.module) return moduleLevel(opened.module);
    const scope = insideScope();
    if (!scope) return { components: [], edges: [] };
    return scope.declared
      ? insideLevel(scope.inside)
      : cardLevel(scope.card, opened.path || []);
  }

  function focusLevel(view, label) {
    if (!label || !view.components.some((card) => card.label === label)) return view;
    const byWeight = (a, b) => weight(b) - weight(a) ||
      a.source.localeCompare(b.source) || a.target.localeCompare(b.target);
    const direct = [
      ...view.edges.filter((edge) => edge.target === label).sort(byWeight),
      ...view.edges.filter((edge) => edge.source === label).sort(byWeight),
    ];
    const edges = [...new Set([...direct, ...view.edges.filter((edge) => edge.state === "violation")])];
    const names = new Set([label, ...edges.flatMap((edge) => [edge.source, edge.target])]);
    return { ...view, components: view.components.filter((card) => names.has(card.label)), edges };
  }

  function level() {
    let view = fullLevel();
    if (viewMode !== "diagram") return view;
    if (diagramFramePath.length && !opened) {
      const frame = diagramPhysicalFrames(view).find((item) => item.id === diagramFramePath.at(-1));
      if (frame) {
        const components = view.components.filter((card) => card.modules.length > 0
          && card.modules.every((name) => inPhysicalScope(name, frame.scope)));
        const labels = new Set(components.map((card) => card.label));
        view = { ...view, components, edges: view.edges.filter((edge) =>
          labels.has(edge.source) && labels.has(edge.target)) };
      }
    }
    return focusLevel(view, focusLabel);
  }

  function inPhysicalScope(name, scope) {
    return typeof name === "string" && typeof scope === "string"
      && (name === scope || name.startsWith(`${scope}.`));
  }

  function diagramPhysicalFrames(view, includeRoot = false) {
    if ((opened && !includeRoot) || !DATA.explorers?.target_diagrams?.root) return [];
    const graph = DATA.explorers.target_diagrams.root;
    const containers = graph.containers || {};
    const frames = Object.entries(containers).flatMap(([id, container]) => {
      const record = targetNode(id);
      return typeof container.scope === "string" && record?.kind === "root_layout"
        ? [{ id, scope: container.scope, label: record.label, parent: container.parent || null }]
        : [];
    });
    const byId = new Map(frames.map((frame) => [frame.id, frame]));
    const visible = new Set();
    const directCards = new Map(frames.map((frame) => [frame.id, []]));
    for (const card of view.components) {
      if (card.library || !card.modules?.length) continue;
      const placement = diagramPlacementFor(card);
      const frame = frames.find((item) => item.id === placement?.container);
      if (!frame || !card.modules.every((name) => inPhysicalScope(name, frame.scope))) continue;
      directCards.get(frame.id).push(card.label);
      for (let current = frame; current; current = current.parent ? byId.get(current.parent) : null) {
        visible.add(current.id);
      }
    }
    return frames.filter((frame) => visible.has(frame.id)).map((frame) => ({
      ...frame,
      parent: visible.has(frame.parent) ? frame.parent : null,
      cards: directCards.get(frame.id).sort(),
    }));
  }

  function layoutDiagramFrames(frames, cards) {
    if (!frames.length) return {};
    const byId = new Map(frames.map((frame) => [frame.id, frame]));
    const topFrame = (frame) => {
      let current = frame;
      while (current.parent && byId.get(current.parent)?.parent) current = byId.get(current.parent);
      return current;
    };
    const cardFrame = new Map(frames.flatMap((frame) => frame.cards.map((label) => [label, frame])));
    const lanes = new Map();
    const laneFor = new Map();
    for (const card of cards) {
      const frame = cardFrame.get(card.label);
      const lane = frame ? topFrame(frame).id : "@unframed";
      if (!lanes.has(lane)) lanes.set(lane, new Map());
      const y = positions[card.label].y;
      if (!lanes.get(lane).has(y)) lanes.get(lane).set(y, []);
      lanes.get(lane).get(y).push(card.label);
      laneFor.set(card.label, lane);
    }
    const orderedLanes = [
      ...frames.filter((frame) => !frame.parent).flatMap((frame) =>
        frames.filter((child) => child.parent === frame.id).map((child) => child.id)
          .concat([frame.id])),
      "@unframed",
    ].filter((lane, index, all) => lanes.has(lane) && all.indexOf(lane) === index);
    let x = 0;
    const lanePositions = new Map();
    for (const lane of orderedLanes) {
      const rows = lanes.get(lane);
      const width = Math.max(1, ...[...rows.values()].map((items) => items.length));
      lanePositions.set(lane, x);
      for (const items of rows.values()) {
        items.sort();
        items.forEach((label, index) => {
          positions[label] = { ...positions[label], x: x + index * (CARD.w + GAP) };
        });
      }
      x += width * (CARD.w + GAP) + GAP;
    }

    const bounds = {};
    const frameChildren = new Map(frames.map((frame) => [frame.id, []]));
    frames.forEach((frame) => {
      if (frame.parent && frameChildren.has(frame.parent)) frameChildren.get(frame.parent).push(frame.id);
    });
    const frameBounds = (id) => {
      const frame = byId.get(id);
      const descendants = [
        ...frame.cards.filter((label) => cards.some((card) => card.label === label))
          .map((label) => ({
            left: positions[label].x,
            top: positions[label].y,
            right: positions[label].x + CARD.w,
            bottom: positions[label].y + CARD.h,
          })),
        ...frameChildren.get(id).map(frameBounds).filter(Boolean),
      ];
      if (!descendants.length) return null;
      const left = Math.min(...descendants.map((item) => item.left)) - 24;
      const right = Math.max(...descendants.map((item) => item.right)) + 24;
      const bottom = Math.max(...descendants.map((item) => item.bottom)) + 24;
      const role = "Physical package";
      const name = compactFrameName(frame.scope, right - left - 28);
      const header = FRAME_HEADER_HEIGHT;
      const top = Math.min(...descendants.map((item) => item.top)) - header;
      bounds[id] = { left, right, top, bottom, header, role, name, scope: frame.scope };
      return bounds[id];
    };
    frames.filter((frame) => !frame.parent).forEach((frame) => frameBounds(frame.id));
    return bounds;
  }

  function renderDiagramFrames(frames, bounds) {
    frameLayer.textContent = "";
    frames.forEach((frame) => {
      const box = bounds[frame.id];
      if (!box) return;
      const selectedFrame = selected?.type === "frame" && selected.id === frame.id;
      const group = el("g", {
        class: `node diagram-frame${selectedFrame ? " selected" : ""}`,
        tabindex: "0",
        role: "button",
        "aria-label": `Select Physical package ${box.name}; navigation grouping, not owner. Canonical scope ${box.scope}`,
        "aria-pressed": String(selectedFrame),
        "data-diagram-frame": frame.id,
        "data-label": frame.id,
      });
      group.appendChild(el("rect", {
        class: "target-frame",
        x: String(box.left),
        y: String(box.top),
        width: String(box.right - box.left),
        height: String(box.bottom - box.top),
        rx: "8",
      }));
      group.appendChild(el("rect", {
        class: "target-frame-header-hit",
        x: String(box.left),
        y: String(box.top),
        width: String(box.right - box.left),
        height: String(box.header),
        rx: "8",
      }));
      frameHeaderText(group, box.role, box.name, box.left + 14, box.top + 37);
      const title = el("title");
      title.textContent = `Physical package ${box.name}. Canonical scope ${box.scope}. Opens a navigation grouping; it is not an owner.`;
      group.appendChild(title);
      const select = () => {
        selected = { type: "frame", id: frame.id };
        selectedSubject = null;
        render();
      };
      group.addEventListener("pointerdown", (event) => {
        event.stopPropagation();
        capturePointer(svg, event);
        framePointer = { id: frame.id, timeStamp: event.timeStamp };
      });
      group.addEventListener("click", (event) => {
        if (event.detail === 0) select();
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          enterDiagramFrame(frame.id);
        } else if (event.key === " ") {
          event.preventDefault();
          select();
        }
      });
      frameLayer.appendChild(group);
    });
  }

  function insideLevel(inside) {
    const cards = inside.components.map((card) => ({
      label: card.label,
      modules: card.modules,
      declared_component: card.declared_component,
      openable: Boolean(card.inside) || card.modules.length > 0,
      public: card.public,
      requires: card.requires || [],
      inside: card.inside,
      declared_inside_component: true,
    }));
    // A module no sub-component owns keeps a card: one that vanished between two levels is
    // exactly what this tool exists to prevent (AD-34). Opening it opens the module itself.
    const orphans = (inside.unassigned || []).map((name) => ({
      label: name,
      display: name.split(".").pop() || name,
      modules: [name],
      openable: Boolean((DATA.modules || {})[name]),
      opensModule: name,
      public: null,
      declared_component: false,
    }));
    return {
      components: cards.concat(orphans),
      edges: inside.edges.map((edge) => ({ ...edge, names: [] })),
      declaredInside: true,
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
        kind: "symbol_use",
        rule_ids: [],
        state: "observed",
        names: [],
      })),
    };
  }
  // One activation selects; explicit open and Enter provide the single-step drill action.
  function selectCard(label) {
    const card = level().components.find((c) => c.label === label);
    if (!card) return;
    selected = { type: "node", label };
    selectSubject(card, "diagram");
    render();
  }

  const edgeKey = (e) => `${e.source}>${e.target}`;
  let positions = {};
  let diagramOrigin = null;
  let sizedPositions = positions;
  const linkedComponent = new URLSearchParams(window.location.hash.slice(1)).get("component");
    let opened = componentByLabel.has(linkedComponent)
    ? { component: linkedComponent, path: [] } : null;
  let selected = null;
  let viewMode = "diagram";
  let focusLabel = null;
  let transform = { k: 1 };
  let projectionPath = [];
  let projectionSelection = null;
  let projectionContext = null;
  let projectionReturnContext = null;
  let targetPath = [];
  let targetSelection = null;
  let diagramFramePath = [];
  let selectedSubject = null;
  const viewStates = new Map();
  const scrollViewport = (view) => ["actual", "diff", "structure", "review"].includes(view)
    ? alternative : canvas;
  const navigationHistory = new Map();

  function saveViewState(view) {
    const scroll = scrollViewport(view);
    viewStates.set(view, {
      opened: opened ? structuredClone(opened) : null,
      selected: selected ? { ...selected } : null,
      focusLabel,
      transform: { ...transform },
      positions: structuredClone(positions),
      projectionPath: [...projectionPath],
      projectionSelection,
      targetPath: [...targetPath],
      targetSelection,
      diagramFramePath: [...diagramFramePath],
      selectedSubject: selectedSubject ? { ...selectedSubject } : null,
      projectionContext,
      projectionReturnContext,
      threshold: thresholdInput.value,
      violationsOnly: violationsOnly.checked,
      scrollLeft: scroll.scrollLeft,
      scrollTop: scroll.scrollTop,
    });
  }

  function restoreViewState(view) {
    const state = viewStates.get(view);
    if (!state) return false;
    opened = state.opened ? structuredClone(state.opened) : null;
    selected = state.selected ? { ...state.selected } : null;
    focusLabel = state.focusLabel;
    transform = { ...state.transform };
    positions = structuredClone(state.positions);
    projectionPath = [...state.projectionPath];
    projectionSelection = state.projectionSelection;
    targetPath = [...state.targetPath];
    targetSelection = state.targetSelection;
    diagramFramePath = [...(state.diagramFramePath || [])];
    selectedSubject = state.selectedSubject ? { ...state.selectedSubject } : null;
    projectionContext = state.projectionContext;
    projectionReturnContext = state.projectionReturnContext;
    thresholdInput.value = state.threshold;
    violationsOnly.checked = state.violationsOnly;
    return true;
  }

  function invalidateOtherViewStates() {
    for (const view of viewStates.keys()) {
      if (view !== viewMode) {
        viewStates.delete(view);
        navigationHistory.delete(view);
      }
    }
  }

  function rememberNavigationState() {
    const scroll = scrollViewport(viewMode);
    const history = navigationHistory.get(viewMode) || [];
    history.push({
      opened: opened ? structuredClone(opened) : null,
      selected: selected ? { ...selected } : null,
      focusLabel,
      transform: { ...transform },
      positions: structuredClone(positions),
      projectionPath: [...projectionPath],
      projectionSelection,
      targetPath: [...targetPath],
      targetSelection,
      diagramFramePath: [...diagramFramePath],
      selectedSubject: selectedSubject ? { ...selectedSubject } : null,
      projectionContext,
      projectionReturnContext,
      threshold: thresholdInput.value,
      violationsOnly: violationsOnly.checked,
      scrollLeft: scroll.scrollLeft,
      scrollTop: scroll.scrollTop,
    });
    navigationHistory.set(viewMode, history);
  }

  function restoreNavigationState() {
    const history = navigationHistory.get(viewMode);
    const state = history?.pop();
    if (!state) return false;
    opened = state.opened ? structuredClone(state.opened) : null;
    selected = state.selected ? { ...state.selected } : null;
    focusLabel = state.focusLabel;
    transform = { ...state.transform };
    positions = structuredClone(state.positions);
    projectionPath = [...state.projectionPath];
    projectionSelection = state.projectionSelection;
    targetPath = [...state.targetPath];
    targetSelection = state.targetSelection;
    diagramFramePath = [...state.diagramFramePath];
    selectedSubject = state.selectedSubject ? { ...state.selectedSubject } : null;
    projectionContext = state.projectionContext;
    projectionReturnContext = state.projectionReturnContext;
    thresholdInput.value = state.threshold;
    violationsOnly.checked = state.violationsOnly;
    render();
    focusCurrentLevel();
    const scroll = scrollViewport(viewMode);
    scroll.scrollLeft = state.scrollLeft;
    scroll.scrollTop = state.scrollTop;
    if (!history.length) navigationHistory.delete(viewMode);
    return true;
  }

  function selectedCanOpen() {
    if (viewMode === "diagram") {
      if (selected?.type === "frame") {
        return diagramPhysicalFrames(fullLevel()).some((item) => item.id === selected.id);
      }
      const card = selected?.type === "node"
        ? level().components.find((item) => item.label === selected.label) : null;
      return Boolean(card && (opened ? card.openable : !card.library));
    }
    if (viewMode === "target") {
      const node = targetNode(targetSelection);
      return Boolean(node?.children?.length && targetGraphFor(targetNode(targetPath.at(-1)))?.owner !== node.id);
    }
    if (["actual", "diff"].includes(viewMode)) {
      const node = projectionNodes(DATA.explorers[viewMode]).find(({ node }) =>
        node.id === projectionSelection)?.node;
      return Boolean(node?.children?.length);
    }
    return false;
  }

  function updateOpenSelected() {
    openSelectedButton.disabled = !selectedCanOpen();
    const frame = viewMode === "diagram" && selected?.type === "frame"
      ? diagramPhysicalFrames(fullLevel()).find((item) => item.id === selected.id) : null;
    const label = viewMode === "diagram" ? frame
      ? `Physical package · navigation grouping: ${frame.scope}` : selected?.label
      : viewMode === "target" ? targetNode(targetSelection)?.label
        : projectionNodes(DATA.explorers[viewMode] || []).find(({ node }) =>
          node.id === projectionSelection)?.node.label;
    const visibleLabel = label || nodeLayer.querySelector(".selected")?.getAttribute("data-label");
    openSelectedButton.setAttribute("aria-label", visibleLabel
      ? "Open selected " + visibleLabel : "Open selected");
  }

  openSelectedButton.addEventListener("click", () => {
    if (!selectedCanOpen()) return;
    if (viewMode === "diagram") {
      if (selected.type === "frame") enterDiagramFrame(selected.id);
      else enter(selected.label);
    } else if (viewMode === "target") {
      const node = targetNode(targetSelection);
      invalidateOtherViewStates();
      rememberNavigationState();
      selectSubject(node);
      targetPath.push(node.id);
      targetSelection = null;
      render();
      focusCurrentLevel();
    } else if (["actual", "diff"].includes(viewMode)) {
      const node = projectionNodes(DATA.explorers[viewMode]).find(({ node }) =>
        node.id === projectionSelection)?.node;
      if (!node) return;
      invalidateOtherViewStates();
      rememberNavigationState();
      selectSubject(node);
      projectionPath.push(node.id);
      projectionSelection = null;
      render();
      focusCurrentLevel();
    }
  });

  function enterDiagramFrame(id) {
    if (!diagramPhysicalFrames(fullLevel()).some((item) => item.id === id)) return;
    selected = { type: "frame", id };
    rememberNavigationState();
    diagramFramePath.push(id);
    selected = null;
    render();
    focusCurrentLevel();
  }

  let expansionRestore = null;
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

  function targetNode(id, nodes = DATA.explorers?.target || []) {
    for (const node of nodes) {
      if (node.id === id) return node;
      const child = targetNode(id, node.children || []);
      if (child) return child;
    }
    return null;
  }

  function targetModulesForFile(file, nodes = DATA.explorers?.target || []) {
    return nodes.flatMap((node) => [
      ...(node.kind === "module_target" && node.details?.some((item) =>
        item.label === "File" && item.value === file) ? [node] : []),
      ...targetModulesForFile(file, node.children || []),
    ]);
  }

  function actualModuleFile(id) {
    const matches = projectionNodes(DATA.explorers?.actual || [])
      .map(({ node }) => node).filter((node) => node.kind === "module" && node.id === id);
    if (matches.length !== 1) return null;
    const file = matches[0].details?.find((item) => item.label === "File")?.value;
    return typeof file === "string" ? file : null;
  }

  function actualModuleIdForFile(file) {
    const matches = projectionNodes(DATA.explorers?.actual || [])
      .map(({ node }) => node).filter((node) => node.kind === "module"
        && node.details?.some((item) => item.label === "File" && item.value === file));
    return matches.length === 1 ? matches[0].id : null;
  }

  function targetNodesForId(id, nodes = DATA.explorers?.target || []) {
    return nodes.flatMap((node) => [
      ...(node.id === id ? [node] : []),
      ...targetNodesForId(id, node.children || []),
    ]);
  }

  function projectionKey(node) {
    if (node.kind === "physical_child") return node.label;
    if (node.kind === "root_layout") return node.label.replaceAll("/", ".");
    if (["module", "group"].includes(node.kind)) return node.id;
    if (node.kind === "component") {
      const packages = node.details?.find((item) => item.label === "Packages")?.value?.split(", ") || [];
      return packages.length === 1 ? packages[0] : null;
    }
    if (node.kind === "package_scope") {
      return node.details?.find((item) => item.label === "Package scope")?.value || node.label;
    }
    const file = node.details?.find((item) => item.label === "File")?.value;
    return typeof file === "string" ? file.replaceAll("/", ".").replace(/\.py$/, "").replace(/\.__init__$/, "") : null;
  }

  function projectionNodes(nodes, parents = []) {
    return nodes.flatMap((node) => {
      const path = [...parents, node];
      return [{ node, path }, ...projectionNodes(node.children || [], path)];
    });
  }

  function diagramDeclarationPath(id, cards = rootCards, parents = []) {
    for (const card of cards) {
      const path = [...parents, card];
      if (card.declared_component === id) return path;
      const nested = diagramDeclarationPath(id, card.inside?.components || [], path);
      if (nested) return nested;
    }
    return null;
  }

  function diagramRouteForCardPath(path, subject) {
    const nested = path.slice(1);
    const opened = nested.length ? {
      component: path[0].label,
      ...(nested.length > 1 ? {
        inside: nested[0].label,
        ...(nested.length > 2 ? { insidePath: nested.slice(1, -1).map((card) => card.label) } : {}),
      } : {}),
      path: [],
    } : null;
    return {
      diagramOpened: opened,
      diagramSelectionLabel: path.at(-1).label,
      subject,
    };
  }

  function diagramCardForObservedNode(source) {
    const modules = rootCards.filter((card) => card.modules?.length);
    if (source.kind === "module") {
      const matches = modules.filter((card) => card.modules.includes(source.id));
      return matches.length === 1 ? matches[0] : null;
    }
    if (source.kind !== "group") return null;
    const matches = modules.filter((card) => card.modules.every((id) =>
      id === source.id || id.startsWith(`${source.id}.`)));
    return matches.length === 1 ? matches[0] : null;
  }

  function diagramComponentPathForModule(id, cards = rootCards, parents = []) {
    const matches = cards.filter((card) => card.modules?.includes(id));
    if (matches.length !== 1) return null;
    const card = matches[0];
    const path = [...parents, card];
    const nested = diagramComponentPathForModule(id, card.inside?.components || [], path);
    return nested || path;
  }

  function diagramPhysicalModulePath(card, id, path = []) {
    for (const child of cardLevel(card, path).components) {
      if (child.opensModule === id || child.label === id) return { path, label: child.label };
      if (child.folder && child.modules?.includes(id)) {
        const nested = diagramPhysicalModulePath(card, id, [...path, child.label]);
        if (nested) return nested;
      }
    }
    return null;
  }

  function diagramRouteForModule(id, file) {
    const path = diagramComponentPathForModule(id);
    if (!path) return null;
    const owner = path.at(-1);
    const physical = diagramPhysicalModulePath(owner, id);
    if (!physical) return null;
    const nested = path.slice(1);
    const diagramOpened = nested.length ? {
      component: path[0].label,
      inside: nested[0].label,
      ...(nested.length > 1 ? { insidePath: nested.slice(1).map((card) => card.label) } : {}),
      ...(!owner.inside ? { physicalInsideCard: true } : {}),
      path: physical.path,
    } : {
      component: path[0].label,
      ...(!owner.inside ? { physicalInsideCard: true } : {}),
      path: physical.path,
    };
    return {
      diagramOpened,
      diagramSelectionLabel: physical.label,
      subject: { file },
    };
  }

  function projectionCounterpart(from, to, context = null) {
    const sourceTree = from === "target" ? DATA.explorers.target : DATA.explorers[from];
    const sourcePath = context?.view === from
      ? context.path : from === "target" ? targetPath : projectionPath;
    const sourceSelection = context?.view === from
      ? context.selection : from === "target" ? targetSelection : projectionSelection;
    const flattened = projectionNodes(sourceTree || []);
    const targetEdge = from === "target" && sourceSelection
      ? targetGraphFor(targetNode(sourcePath.at(-1)))?.edges.find((item) =>
        (item.declaration || `${item.source}>${item.target}`) === sourceSelection)
      : null;
    const subject = context?.view === "diagram" ? context.subject : selectedSubject;
    const diagramModuleId = subject?.file ? actualModuleIdForFile(subject.file) : null;
    const sourceNodes = from === "diagram"
      ? subject?.id ? [{ ...targetNode(subject.id), id: subject.id, kind: "component",
        details: targetNode(subject.id)?.details || [] }] : subject?.file && diagramModuleId ? [{ id: diagramModuleId, kind: "module", details: [
        { label: "File", value: subject.file },
      ] }] : subject?.package ? [{ id: subject.package, kind: "group", details: [
        { label: "Package scope", value: subject.package },
      ] }] : []
      : sourcePath.map((id) => flattened.find(({ node }) => node.id === id)?.node).filter(Boolean);
    if (from === "target" && sourceSelection) {
      const graph = targetGraphFor(targetNode(sourcePath.at(-1)));
      const endpoint = graph?.nodes.find((item) => item.id === targetEdge?.target);
      if (endpoint) sourceNodes.push(endpoint);
    }
    if (from !== "diagram" && sourceSelection) {
      const selected = flattened.find(({ node }) => node.id === sourceSelection)?.node;
      if (selected) sourceNodes.push(selected);
    }
    if (!sourceNodes.length) return null;

    if (to === "diagram" && ["actual", "diff", "target"].includes(from)) {
      for (const source of [...sourceNodes].reverse()) {
        if (from === "actual" && !sourceSelection && source.id === sourcePath.at(-1)
            && source.kind === "module" && source.children?.length) {
          const frames = diagramPhysicalFrames({ components: rootCards }, true)
            .filter((frame) => frame.scope === source.id);
          if (frames.length === 1) return { diagramFramePath: [frames[0].id] };
          if (frames.length > 1) return null;
        }
        if (from === "target" && source.kind === "module_target") {
          const file = source.details?.find((item) => item.label === "File")?.value;
          const id = typeof file === "string" ? actualModuleIdForFile(file) : null;
          const route = id && diagramRouteForModule(id, file);
          if (route) return route;
        }
        const declarationId = source.details?.find((item) => item.label === "Target declaration ID")?.value
          || (from === "target" && source.kind === "component" ? source.id : null);
        if (!declarationId) continue;
        const path = diagramDeclarationPath(declarationId);
        if (path) return diagramRouteForCardPath(path, { id: declarationId });
      }
      if (from === "actual") {
        for (const source of [...sourceNodes].reverse()) {
          if (source.kind === "module") {
            const file = actualModuleFile(source.id);
            if (file && targetModulesForFile(file).length === 1) {
              const route = diagramRouteForModule(source.id, file);
              if (route) return route;
            }
          }
          const card = diagramCardForObservedNode(source);
          if (!card) continue;
          const subject = card.declared_component
            ? { id: card.declared_component }
            : source.kind === "module" ? { file: actualModuleFile(source.id) }
              : { package: source.id };
          return diagramRouteForCardPath([card], subject);
        }
      }
      const frames = diagramPhysicalFrames({ components: rootCards });
      for (const source of [...sourceNodes].reverse()) {
        const key = projectionKey(source);
        if (!key) continue;
        const matches = frames.filter((frame) =>
          key === frame.scope || key.startsWith(`${frame.scope}.`));
        const deepestScope = Math.max(0, ...matches.map((frame) => frame.scope.length));
        const best = matches.filter((frame) => frame.scope.length === deepestScope);
        if (best.length === 1) return { diagramFramePath: [best[0].id] };
      }
      return null;
    }

    const candidates = projectionNodes(DATA.explorers[to] || []);
    for (const source of [...sourceNodes].reverse()) {
      const declarationId = source.details?.find((item) => item.label === "Target declaration ID")?.value
        || (from === "target" ? source.id : null);
      const identityMatches = declarationId ? candidates.filter(({ node }) =>
        node.id === declarationId || node.details?.some((item) =>
          item.label === "Target declaration ID" && item.value === declarationId)) : [];
      const key = projectionKey(source);
      if (!key && !identityMatches.length) continue;
      const keys = [key];
      let ancestor = key || "";
      while (ancestor.includes(".")) {
        ancestor = ancestor.slice(0, ancestor.lastIndexOf("."));
        keys.push(ancestor);
      }
      for (const candidateKey of keys) {
        const exactIdentity = candidateKey === key && identityMatches.length > 0;
        const matches = exactIdentity ? identityMatches
          : candidates.filter(({ node }) => candidateKey && projectionKey(node) === candidateKey);
        if (!matches.length) continue;
        if (exactIdentity && matches.length !== 1) continue;
        const rank = (node) => {
          if (["module", "module_target"].includes(source.kind)) {
            return node.kind === "module_target" ? 5 : node.kind === "module" ? 4
              : node.kind === "package_scope" ? 3 : node.kind === "component" ? 2 : 1;
          }
          return node.kind === "package_scope" ? 5 : node.kind === "component" ? 4
            : node.kind === "physical_child" || node.kind === "root_layout" ? 3 : 1;
        };
        const bestRank = Math.max(...matches.map(({ node }) => rank(node)));
        let best = matches.filter(({ node }) => rank(node) === bestRank);
        if (best.length > 1 && candidateKey === key) {
          const sameIdentity = best.filter(({ node }) => node.id === source.id);
          if (sameIdentity.length === 1) best = sameIdentity;
        }
        if (best.length !== 1) continue;
        const match = best[0];
        const selectionWithoutScope = !projectionKey(sourceNodes.at(-1))
          && !(exactIdentity && source === sourceNodes.at(-1));
        const context = targetEdge?.kind === "requires"
          ? `No matching scope for requires; showing nearest match ${candidateKey}.`
          : candidateKey === key && !selectionWithoutScope ? null
          : `No matching scope for ${selectionWithoutScope ? sourceNodes.at(-1).label : key}; showing nearest match ${candidateKey}.`;
        const scopePath = match.node.children?.length ? match.path : match.path.slice(0, -1);
        if (to === "target") {
          const targetPath = scopePath
            .filter(({ id }) => DATA.explorers.target_diagrams.nested[id])
            .map((node) => node.id);
          return {
            targetPath,
            targetSelection: match.node.children?.length ? null : match.node.id,
            context,
          };
        }
        return {
          path: scopePath.map((node) => node.id),
          selection: match.node.children?.length ? null : match.node.id,
          context,
        };
      }
    }
    return null;
  }

  function targetComponentsForPackage(scope, nodes = DATA.explorers?.target || []) {
    return nodes.flatMap((node) => [
      ...(node.kind === "component" && node.children?.some((child) =>
        child.kind === "package_scope" && child.details?.some((item) =>
          item.label === "Package scope" && item.value === scope)) ? [node] : []),
      ...targetComponentsForPackage(scope, node.children || []),
    ]);
  }

  const responsibilityRows = [];
  function collectResponsibilities(nodes, ancestors = []) {
    for (const node of nodes) {
      if (["component", "module_target"].includes(node.kind)) {
        for (const detail of node.details || []) {
          if (detail.label !== "Responsibility") continue;
          responsibilityRows.push({
            id: node.id,
            ancestors: ancestors.map((parent) => parent.id),
            kind: node.kind === "component" ? "Component" : "Module",
            name: node.label,
            path: node.kind === "module_target"
              ? String(node.details.find((item) => item.label === "File")?.value || node.label)
              : [...ancestors.map((parent) => parent.label), node.label].join(" / "),
            sentence: String(detail.value ?? ""),
            missing: detail.missing === true,
          });
        }
      }
      collectResponsibilities(node.children || [], [...ancestors, node]);
    }
  }
  collectResponsibilities(DATA.explorers?.target || []);

  function selectSubject(node, view = viewMode) {
    if (!node) return;
    invalidateOtherViewStates();
    projectionContext = null;
    projectionReturnContext = null;
    selectedSubject = null;
    if (view === "diagram") {
      if (node.declared_component) {
        selectedSubject = { id: node.declared_component };
        return;
      }
      const modules = node.modules || [];
      if (!node.folder && modules.length === 1) {
        const file = actualModuleFile(modules[0]);
        if (file) selectedSubject = { file };
      }
      if (!selectedSubject && modules.length) {
        const placement = diagramPlacementFor(node);
        if (placement.declaration) {
          selectedSubject = { id: placement.declaration };
          return;
        }
        const components = projectionNodes(DATA.explorers?.target || [])
          .map(({ node: item }) => item)
          .filter((item) => item.kind === "component");
        const scopes = components.flatMap((component) =>
          (component.children || [])
            .filter((child) => child.kind === "package_scope")
            .flatMap((child) => child.details || [])
            .filter((detail) => detail.label === "Package scope")
            .map((detail) => String(detail.value))
            .filter((scope) => modules.every((name) =>
              name === scope || name.startsWith(`${scope}.`))));
        const uniqueScopes = [...new Set(scopes)];
        if (uniqueScopes.length === 1) selectedSubject = { package: uniqueScopes[0] };
        else selectedSubject = { id: node.label };
      }
    } else if (["actual", "diff"].includes(view)
        && ["module", "observed_only_module_target"].includes(node.kind)) {
      selectedSubject = { file: node.details?.find((item) => item.label === "File")?.value };
    } else if (view === "actual" && node.kind === "group") {
      selectedSubject = { package: node.id };
    } else if (node.kind === "module_target") {
      selectedSubject = { file: node.details?.find((item) => item.label === "File")?.value || node.label };
    } else if (view === "diff" && node.kind === "component") {
      selectedSubject = {
        id: node.details?.find((item) => item.label === "Target declaration ID")?.value || node.id,
      };
    } else if (["component", "module_target"].includes(node.kind)) {
      selectedSubject = { id: node.id };
    }
  }

  function diagramPlacementFor(card) {
    if (!card.modules?.length) return card.declared_component
      ? { status: "no-observed-modules", scopes: [], declaration: card.declared_component }
      : null;
    const declarationMatches = card.declared_component
      ? targetNodesForId(card.declared_component).filter((node) => node.kind === "component")
      : [];
    const declaration = declarationMatches.length === 1 ? declarationMatches[0] : null;
    if (!declaration) return {
      status: card.declared_component ? "no-unique-declaration" : "no-matching-declaration",
      scopes: [],
    };
    const diagrams = DATA.explorers.target_diagrams || {};
    const graphs = [diagrams.root, ...Object.values(diagrams.nested || {})].filter(Boolean);
    const placement = graphs.flatMap((graph) => graph.nodes || [])
      .find((node) => node.id === declaration.id)?.placement;
    const container = placement?.container || null;
    const frame = container && Object.entries(DATA.explorers.target_diagrams.root.containers || {})
      .find(([id]) => id === container)?.[1];
    if (!container || !frame) return {
      status: placement?.status || "unmapped",
      scopes: placement?.scopes || [],
      declaration: declaration.id,
      provenance: declaration.details?.find((detail) => detail.label === "Declared in")?.value || null,
      container: null,
    };
    if (!card.modules.every((module) => inPhysicalScope(module, frame.scope))) return {
      status: "outside-declared-frame",
      scopes: placement?.scopes || [],
      declaration: declaration.id,
      provenance: declaration.details?.find((detail) => detail.label === "Declared in")?.value || null,
      container: null,
    };
    return {
      status: placement?.status || "unmapped",
      scopes: placement?.scopes || [],
      container,
      declaration: declaration.id,
      provenance: declaration.details?.find((detail) => detail.label === "Declared in")?.value || null,
    };
  }

  function renderSelectedResponsibility() {
    let matches = [];
    if (selectedSubject?.package) {
      matches = targetComponentsForPackage(selectedSubject.package);
    } else if (selectedSubject?.id) {
      matches = targetNodesForId(selectedSubject.id)
        .filter((node) => node.kind === "component");
    } else if (selectedSubject?.file) {
      matches = targetModulesForFile(selectedSubject.file);
    }
    const heading = selectedResponsibility.querySelector("h3");
    const body = selectedResponsibility.querySelector("p");
    const matchStatus = selectedResponsibility.querySelector(".flow-responsibility-match");
    const inView = (nodes, predicate) => nodes.some((node) =>
      predicate(node) || inView(node.children || [], predicate));
    const hasCurrentEntry = ["actual", "target", "diff", "diagram"].includes(viewMode)
      && (selectedSubject?.package
        ? inView(DATA.explorers?.[viewMode === "diagram" ? "actual" : viewMode] || [], (node) =>
          (["actual", "diagram"].includes(viewMode)
            ? node.kind === "group" && node.id === selectedSubject.package
            : node.details?.some((item) =>
              item.label === "Package scope" && item.value === selectedSubject.package)))
        : selectedSubject?.id
        ? (["target", "diff"].includes(viewMode)
          && inView(DATA.explorers?.[viewMode] || [], (node) =>
            node.id === selectedSubject.id || node.details?.some((item) =>
              item.label === "Target declaration ID" && item.value === selectedSubject.id))
          || viewMode === "diagram" && level().components.some((card) =>
            diagramPlacementFor(card)?.declaration === selectedSubject.id))
        : selectedSubject?.file
          && (viewMode === "diagram"
            ? level().components.some((card) => !card.folder
              && (card.modules || []).some((module) =>
                actualModuleFile(module) === selectedSubject.file))
            : inView(DATA.explorers?.[viewMode] || [], (node) =>
              node.details?.some((item) => item.label === "File" && item.value === selectedSubject.file)))
      );
    selectedResponsibility.hidden = !selectedSubject;
    selectedResponsibility.dataset.declarationId = matches.length === 1 ? matches[0].id : "";
    if (selected?.type === "frame") {
      selectedResponsibility.hidden = false;
      heading.textContent = "Physical navigation frame";
      body.textContent = "No declared responsibility; this grouping does not represent a component.";
    } else if (!selectedSubject) {
      body.textContent = "Select a component or module to inspect its declared responsibility.";
    } else if (matches.length === 0) {
      body.textContent = "No matching target declaration.";
    } else if (matches.length > 1) {
      body.textContent = "No unique declaration match.";
    } else {
      const details = matches[0].details?.filter((item) => item.label === "Responsibility") || [];
      const missing = !details.length || details.every((item) => item.missing === true);
      heading.textContent = missing ? "Missing responsibility" : "Declared responsibility";
      body.textContent = missing ? "No declared responsibility."
        : details.filter((item) => !item.missing).map((item) => String(item.value || "")).join(" ");
    }
    if (matches.length !== 1) heading.textContent = "Declared responsibility";
    selectedResponsibility.dataset.selected = String(!selectedResponsibility.hidden);
    matchStatus.textContent = selectedSubject && !hasCurrentEntry
      ? "No matching entry in this view; this declaration remains target information."
      : "";
  }

  function diagramResponsibilities(card) {
    const declaration = card.declared_component
      ? targetNode(card.declared_component)
      : null;
    const file = !card.folder && card.modules?.length === 1
      ? actualModuleFile(card.modules[0]) : null;
    const moduleMatches = file
      ? targetModulesForFile(file)
      : [];
    const responsibilityNode = declaration || (moduleMatches.length === 1 ? moduleMatches[0] : null);
    return (responsibilityNode?.details || [])
      .filter((detail) => detail.label === "Responsibility" && !detail.missing && detail.value)
      .map((detail) => String(detail.value));
  }

  function filterResponsibilities() {
    const query = responsibilitySearch.value.trim().toLocaleLowerCase();
    let shown = 0;
    responsibilityList.querySelectorAll("button").forEach((button) => {
      const row = responsibilityRows[Number(button.dataset.responsibilityIndex)];
      button.hidden = !`${row.kind} ${row.path} ${row.missing ? "No declared responsibility" : row.sentence}`
        .toLocaleLowerCase().includes(query);
      if (!button.hidden) shown += 1;
    });
    responsibilityCount.textContent = `${shown} of ${responsibilityRows.length} shown`;
  }

  function renderResponsibilities() {
    if (responsibilityList.childElementCount) return;
    const declared = responsibilityRows.filter((row) => !row.missing).length;
    const missing = responsibilityRows.length - declared;
    responsibilities.querySelector(".flow-responsibility-total").textContent =
      `(${declared} declared · ${missing} missing)`;
    responsibilityList.innerHTML = responsibilityRows.map((row, index) =>
      `<button type="button" data-responsibility-index="${index}">` +
      `<span><small>${esc(row.kind)}</small><strong>${esc(row.name)}</strong>` +
      `<code>${esc(row.path)}</code></span>` +
      `<span>${esc(row.missing ? "No declared responsibility" : row.sentence)}</span></button>`).join("");
    filterResponsibilities();
  }

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
    const view = level();
    if (viewMode === "diagram" && focusLabel && view.components.length) {
      const incoming = [...new Set(view.edges.filter((edge) => edge.target === focusLabel)
        .map((edge) => edge.source))].filter((name) => name !== focusLabel).sort();
      const outgoing = [...new Set(view.edges.filter((edge) => edge.source === focusLabel)
        .map((edge) => edge.target))].filter((name) => name !== focusLabel && !incoming.includes(name)).sort();
      const other = view.components.map((card) => card.label).filter((name) =>
        name !== focusLabel && !incoming.includes(name) && !outgoing.includes(name));
      const rows = Math.max(incoming.length, outgoing.length, 1);
      const rowPitch = CARD.h + GAP;
      const centerY = (rows - 1) * rowPitch / 2;
      if (!positions[focusLabel]) positions[focusLabel] = { x: 0, y: centerY };
      incoming.forEach((name, index) => {
        if (!positions[name]) positions[name] = { x: -310, y: index * rowPitch };
      });
      outgoing.forEach((name, index) => {
        if (!positions[name]) positions[name] = { x: 310, y: index * rowPitch };
      });
      other.forEach((name, index) => {
        if (!positions[name]) {
          positions[name] = {
            x: (index % 2 ? 310 : -310), y: (rows + Math.floor(index / 2)) * rowPitch,
          };
        }
      });
      return rows + Math.ceil(other.length / 2);
    }
    const rank = computeRanks();
    const byRank = groupBy(level().components, (c) => rank.get(c.label));
    const ranks = [...byRank.keys()].sort((a, b) => a - b);
    let row = 0;
    ranks.forEach((r) => {
      const members = byRank.get(r).map((c) => c.label).sort();
      for (let start = 0; start < members.length; start += PER_ROW) {
        const chunk = members.slice(start, start + PER_ROW);
        const total = chunk.length * CARD.w + (chunk.length - 1) * GAP;
        chunk.forEach((label, index) => {
          if (!positions[label]) {
            positions[label] = { x: index * (CARD.w + GAP) - total / 2, y: row * (CARD.h + ROW_GAP) };
          }
        });
        row += 1;
      }
    });
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
    edge, outIndex, inIndex, outCount, inCount, laneOffset, headers = [], frames = {},
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
    const sy = sourceAnchor?.y;
    const ty = targetAnchor?.y;
    const upward = (ty ?? tPos.y) < (sy ?? sPos.y);
    if (sameRow) {
      const sy = sPos.y + CARD.h;
      const drop = sy + 56 + Math.abs(laneOffset) + (laneOffset < 0 ? LANE_GAP / 2 : 0);
      const dir = Math.sign(tx - sx) || 1;
      const end = sy + 6;
      const points = [[sx, sy], [sx, drop], [tx, drop], [tx, end]];
      const direct = {
        d: `M${sx},${sy} V${drop - 8} Q${sx},${drop} ${sx + dir * 8},${drop} H${tx - dir * 8} Q${tx},${drop} ${tx},${drop - 8} V${end}`,
        mid: [(sx + tx) / 2, drop], end: [tx, end],
      };
      return routeAroundHeaders(direct, points, sx, sy, tx, end, headers, edge, frames);
    }
    const startY = sy ?? (upward ? sPos.y : sPos.y + CARD.h);
    const endY = ty ?? (upward ? tPos.y + CARD.h : tPos.y);
    const my = (startY + endY) / 2 + laneOffset;
    const dir = Math.sign(tx - sx);
    const vdir = Math.sign(endY - startY) || 1;
    const r = Math.min(10, Math.abs(tx - sx) / 2);
    const end = targetAnchor ? endY : endY - vdir * 6;
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
    const rounded = dir === 0
      ? `M${sx},${startY} V${end}`
      : `M${sx},${startY} V${my - vdir * r} Q${sx},${my} ${sx + dir * r},${my} H${tx - dir * r} Q${tx},${my} ${tx},${my + vdir * r} V${end}`;
    const direct = {
      d: sourceAnchor || targetAnchor ? orthogonalPath(points) : rounded,
      mid: [(sx + tx) / 2, my],
      end: finish,
    };
    return routeAroundHeaders(direct, points, sx, startY, tx, end, headers, edge, frames);
  }

  function routeAroundHeaders(direct, points, sx, sy, tx, end, headers, edge, frames) {
    if (!headers.length || routePointsClear(points, headers, 10)) return direct;
    const cards = Object.entries(positions).filter(([id, position]) =>
      !frames[id] && Number.isFinite(position.x) && Number.isFinite(position.y));
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
      allLeft - 14,
      allRight + 14,
    ])];
    const sourceCard = frames[edge.source] ? null : positions[edge.source];
    const targetCard = frames[edge.target] ? null : positions[edge.target];
    const sourceDirection = Math.sign(points[1]?.[1] - sy) || Math.sign(end - sy) || 1;
    const endDirection = Math.sign(end - points.at(-2)?.[1]) || Math.sign(end - sy) || 1;
    const normalSource = frames[edge.source]
      ? { point: [sx, sy], lead: points[1], axis: "horizontal" }
      : { point: [sx, sy], lead: [sx, sy + sourceDirection * 14], axis: "vertical" };
    const normalTarget = frames[edge.target]
      ? { point: [tx, end], lead: points.at(-2), axis: "horizontal" }
      : { point: [tx, end], lead: [tx, end - endDirection * 14], axis: "vertical" };
    const sourceBlocked = !routePointsClear(
      [normalSource.point, normalSource.lead], headers, 2,
    );
    const targetBlocked = !routePointsClear(
      [normalTarget.lead, normalTarget.point], headers, 2,
    );
    const sourcePorts = sourceBlocked && sourceCard
      ? ["left", "right"].map((side) => {
        const x = side === "left" ? sourceCard.x : sourceCard.x + CARD.w;
        return { point: [x, sourceCard.y + CARD.h / 2],
          lead: [x + (side === "left" ? -14 : 14), sourceCard.y + CARD.h / 2], axis: "horizontal" };
      })
      : [normalSource];
    const targetPorts = targetBlocked && targetCard
      ? [
        ...["left", "right"].map((side) => {
          const x = side === "left" ? targetCard.x : targetCard.x + CARD.w;
          return { point: [x, targetCard.y + CARD.h / 2],
            lead: [x + (side === "left" ? -14 : 14), targetCard.y + CARD.h / 2], axis: "horizontal" };
        }),
        { point: [targetCard.x + CARD.w / 2, targetCard.y + CARD.h],
          lead: [targetCard.x + CARD.w / 2, targetCard.y + CARD.h + 14], axis: "vertical" },
      ]
      : [normalTarget];
    const sourceLanes = [...new Set([
      normalSource.lead[1], normalTarget.lead[1],
      ...Object.values(positions).filter((position) => Number.isFinite(position.y)).flatMap((position) => [
        position.y - 14, position.y + CARD.h + 14,
      ]),
      ...headers.flatMap((header) => [header.top - 14, header.bottom + 14]),
    ])];
    const routes = [];
    for (const source of sourcePorts) {
      for (const target of targetPorts) {
        for (const gutterX of gutters) {
          for (const laneY of sourceLanes) {
            routes.push({
              points: [
                source.point, source.lead, [source.lead[0], laneY], [gutterX, laneY],
                [gutterX, target.lead[1]], target.lead, target.point,
              ],
              end: target.point,
            });
          }
        }
      }
    }
    const cardsClear = (route) => Object.entries(positions).every(([id, position]) => {
      if (frames[id] || !Number.isFinite(position.x) || !Number.isFinite(position.y)) return true;
      return route.slice(1).every((point, index) => {
        const [x1, y1] = route[index];
        const [x2, y2] = point;
        const left = position.x, right = position.x + CARD.w;
        const top = position.y, bottom = position.y + CARD.h;
        if (x1 === x2) return x1 <= left || x1 >= right
          || Math.max(y1, y2) <= top || Math.min(y1, y2) >= bottom;
        if (y1 === y2) return y1 <= top || y1 >= bottom
          || Math.max(x1, x2) <= left || Math.min(x1, x2) >= right;
        return false;
      });
    });
    const clear = routes.filter((route) => routePointsClear(route.points, headers, 2)
      && cardsClear(route.points));
    if (!clear.length) return { ...direct, routingWarning: true };
    clear.sort((left, right) => {
      const length = ({ points: route }) => route.slice(1).reduce((total, point, index) =>
        total + Math.abs(point[0] - route[index][0]) + Math.abs(point[1] - route[index][1]), 0);
      return length(left) - length(right);
    });
    const route = clear[0];
    return {
      d: orthogonalPath(route.points),
      mid: route.points[Math.floor(route.points.length / 2)],
      end: route.end,
    };
  }

  function weight(edge) {
    return edge.kind === "symbol_use" ? 1 : edge.import_sites;
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

  function activeFilterSummary(mode) {
    if (["actual", "target", "diff"].includes(mode)) return "";
    const active = [];
    if (focusLabel) active.push(`Focus: ${focusLabel}`);
    if (Number(thresholdInput.value) > 0) {
      const unit = opened?.module ? "symbol-use edges" : "import sites";
      active.push(`edges with at least ${thresholdInput.value} ${unit}`);
    }
    if (violationsOnly.checked) active.push("violating edges only");
    return active.length ? `Active filters: ${active.join("; ")}` : "No diagram filters active";
  }

  function normalizeThreshold(maximum) {
    thresholdInput.max = String(maximum || 1);
    if (Number(thresholdInput.value) > maximum) thresholdInput.value = String(maximum);
    thresholdInput.disabled = violationsOnly.checked;
  }

  function updateEdgeCount(shown, total) {
    thresholdValue.textContent =
      `Edges shown / at this level: ${shown}/${total} · ` +
      `show ≥ ${thresholdInput.value} ${opened?.module ? "symbol-use edges" : "import sites"}`;
  }

  function related(edge) {
    if (!selected) return true;
    if (selected.type === "node") return edge.source === selected.label || edge.target === selected.label;
    if (selected.type === "frame") return true;
    return edgeKey(edge) === selected.key;
  }

  function relatedToSelection(label) {
    if (!selected) return true;
    if (selected.type === "node") {
      return label === selected.label || level().edges.some((e) => related(e) && (e.source === label || e.target === label));
    }
    if (selected.type === "frame") return true;
    const [source, target] = selected.key.split(">");
    return label === source || label === target;
  }

  function capturedFocus() {
    const node = document.activeElement.closest(".node");
    if (node?.hasAttribute("data-diagram-frame")) {
      return { kind: "frame", key: node.getAttribute("data-diagram-frame") };
    }
    if (node) return { kind: "node", key: node.getAttribute("data-label") };
    if (document.activeElement.classList.contains("chip")) {
      return { kind: "chip", key: document.activeElement.getAttribute("data-key") };
    }
    if (document.activeElement.classList.contains("hit")) {
      return { kind: "edge", key: document.activeElement.getAttribute("data-key") };
    }
    return null;
  }

  function restoreFocus(focused) {
    if (!focused) return;
    const attr = focused.kind === "node" ? "data-label" : "data-key";
    const selector = `[${attr}="${CSS.escape(focused.key)}"]`;
    const layer = focused.kind === "frame" ? frameLayer
      : focused.kind === "node" ? nodeLayer
        : focused.kind === "chip" ? chipLayer : edgeLayer;
    const target = focused.kind === "frame"
      ? layer.querySelector(`[data-diagram-frame="${CSS.escape(focused.key)}"]`)
      : layer.querySelector(selector);
    if (target) target.focus();
  }

  function focusCurrentLevel() {
    const target = viewMode === "diagram"
      ? selected?.type === "node"
        ? nodeLayer.querySelector(`[data-label="${CSS.escape(selected.label)}"]`)
        : selected?.type === "frame"
          ? frameLayer.querySelector(`[data-diagram-frame="${CSS.escape(selected.id)}"]`)
          : nodeLayer.querySelector(".node") || frameLayer.querySelector(".node")
      : viewMode === "target"
        ? targetSelection
          ? nodeLayer.querySelector(`[data-target-node="${CSS.escape(targetSelection)}"]`)
          : nodeLayer.querySelector(".target-node:not(.target-container)")
          || nodeLayer.querySelector(".target-container")
        : viewMode === "structure"
          ? selected?.type === "node"
            ? alternative.querySelector(`[data-flow-card="${CSS.escape(selected.label)}"]`)
            : alternative.querySelector("[data-flow-card]")
          : projectionSelection
          ? alternative.querySelector(`[data-projection-id="${CSS.escape(projectionSelection)}"]`)
          : alternative.querySelector("[data-projection-id]");
    (target || flowHeading).focus({ preventScroll: true });
  }

  function captureAlternativeFocus() {
    const button = document.activeElement.closest(
      "[data-flow-card], [data-flow-edge], [data-key], [data-projection-id], [data-projection-crumb], [data-projection-root]",
    );
    if (!button || !alternative.contains(button)) return null;
    return button.dataset.flowCard !== undefined
      ? { attribute: "data-flow-card", value: button.dataset.flowCard }
      : button.dataset.flowEdge !== undefined
        ? { attribute: "data-flow-edge", value: button.dataset.flowEdge }
        : button.dataset.key !== undefined
          ? { attribute: "data-key", value: button.dataset.key }
          : button.dataset.projectionId !== undefined
            ? { attribute: "data-projection-id", value: button.dataset.projectionId }
            : button.dataset.projectionCrumb !== undefined
              ? { attribute: "data-projection-crumb", value: button.dataset.projectionCrumb }
              : { attribute: "data-projection-root", value: "" };
  }

  function restoreAlternativeFocus(focused) {
    if (!focused) return;
    const target = alternative.querySelector(
      `[${focused.attribute}="${CSS.escape(focused.value)}"]`,
    );
    if (target) target.focus();
    else {
      const heading = alternative.querySelector("h2");
      if (heading) {
        heading.tabIndex = -1;
        heading.focus();
      }
    }
  }

  function renderTargetInspector(graph) {
    const node = targetSelection ? targetNode(targetSelection) : targetNode(targetPath.at(-1));
    const routeWarning = targetSelection
      ? routeWarningMarkup("data-target-edge", targetSelection) : "";
    const graphNode = graph?.nodes.find((item) => item.id === node?.id);
    const container = node ? graph?.containers?.[node.id] : null;
    const placement = graphNode?.kind === "component" ? graphNode.placement : null;
    const context = projectionContext
      ? `<p class="flow-projection-context">Context: ${esc(projectionContext)}</p>` : "";
    const children = (node?.children || DATA.explorers?.target || [])
      .filter((child) => ["component", "module_target"].includes(child.kind));
    const overview = children.length
      ? `<h3>Responsibilities at this level</h3><ul class="plain target-responsibility-overview">${children.map((child) => {
        const sentence = child.details?.find((detail) => detail.label === "Responsibility")?.value
          || "No responsibility declared.";
        return `<li><strong>${esc(child.label)}</strong><span>${esc(sentence)}</span></li>`;
      }).join("")}</ul>`
      : "";
    if (!node) {
      inspectorContent.innerHTML = `${context}<p>Select a declared component or package for its contract details.</p>${overview}${routeWarning}`;
      return;
    }
    const kind = node.kind === "module_target" ? "Declared module"
      : node.kind === "folder" ? "Folder" : `Declared ${node.kind}`;
    const placementReasons = {
      ambiguous: "Multiple frame matches remain ambiguous in this view.",
      multiple: "These scopes do not share one drawable frame in this view.",
      unmapped: "No drawable frame resolves these scopes in this view.",
    };
    const placementDetails = placement ? (() => {
      const scopes = Array.isArray(placement.scopes)
        ? placement.scopes.filter((scope) => typeof scope === "string") : [];
      const folded = Array.isArray(placement.folded) ? placement.folded : [];
      const reason = placement.container === null
        ? folded.length
          ? "No drawable frame is associated in this view; the matching frame was folded."
          : placementReasons[placement.status] || "No drawable frame is associated in this view."
        : "";
      const foldedMarkup = folded.map((frame) => {
        const details = Array.isArray(frame.details) ? frame.details : [];
        const detailMarkup = details.length
          ? `<ul class="plain">${details.map((detail) =>
            `<li>${esc(detail.label)}: ${esc(detail.value)}</li>`
          ).join("")}</ul>` : "";
        return `<li><strong>${esc(frame.id)}</strong> — ${esc(frame.scope)}${detailMarkup}</li>`;
      }).join("");
      return `<h3>Placement</h3><dl class="kv target-placement">
        <dt>Status</dt><dd>${esc(placement.status)}</dd>
        <dt>Scopes</dt><dd>${scopes.length ? scopes.map(esc).join(", ") : "No declared scopes."}</dd>
        <dt>Container</dt><dd>${placement.container === null
          ? "Unplaced" : esc(placement.container)}</dd>
        ${reason ? `<dt>Reason</dt><dd>${esc(reason)}</dd>` : ""}
        ${foldedMarkup ? `<dt>Folded frames</dt><dd><ul class="plain">${foldedMarkup}</ul></dd>` : ""}
      </dl>`;
    })() : "";
    inspectorContent.innerHTML = `<div class="kicker">${esc(kind)}</div>
      <h2>${esc(node.label)}</h2>
      ${(node.details || []).length
        ? `<dl class="kv">${node.details.map((item) =>
          `<dt>${esc(item.missing ? "Missing responsibility" : item.label)}</dt>` +
          `<dd>${esc(item.missing ? "No declared responsibility." : item.value)}</dd>`
        ).join("")}${container?.scope
          ? `<dt>Canonical scope</dt><dd><code>${esc(container.scope)}</code></dd>` : ""}</dl>`
        : container?.scope
          ? `<dl class="kv"><dt>Canonical scope</dt><dd><code>${esc(container.scope)}</code></dd></dl>`
        : "<p>No additional details recorded.</p>"}${placementDetails}${context}${overview}${routeWarning}`;
  }

  function targetCardMetrics(graphNodes) {
    const metrics = new Map();
    let maxHeight = 92;
    for (const node of graphNodes) {
      const nameLines = wrapText(node.label, CARD.w - 32, `600 15px ${sansFontFamily}`);
      const responsibilityDetails = (node.details || [])
        .filter((item) => item.label === "Responsibility" && !item.missing && item.value)
        .map((item) => wrapText(String(item.value), CARD.w - 32, `13px ${sansFontFamily}`));
      const missingResponsibility = !(node.details || []).some(
        (item) => item.label === "Responsibility" && !item.missing && item.value,
      ) && (node.details || []).some((item) => item.label === "Responsibility" && item.missing);
      const missingLines = missingResponsibility
        ? wrapText("No declared responsibility.", CARD.w - 32, `13px ${sansFontFamily}`)
        : [];
      const responsibilityLineCount = responsibilityDetails.reduce((sum, lines) => sum + lines.length, 0)
        + missingLines.length;
      const responsibilityY = 70 + (nameLines.length - 1) * 18;
      const responsibilityGaps = Math.max(
        0, responsibilityDetails.length + (missingLines.length ? 1 : 0) - 1,
      ) * 2;
      const countY = responsibilityY + responsibilityLineCount * 15 + responsibilityGaps + 5;
      const height = Math.max(92, countY + 25);
      metrics.set(node.id, {
        nameLines, responsibilities: responsibilityDetails, missingLines,
        responsibilityY, countY, height,
      });
      maxHeight = Math.max(maxHeight, height);
    }
    CARD.h = maxHeight;
    TARGET_FRAME_HEADER_ALLOWANCE = FRAME_HEADER_HEIGHT;
    return metrics;
  }

  function targetLayout(graph, graphNodes) {
    const containers = graph?.containers || {};
    const children = new Map(Object.keys(containers).map((id) => [id, []]));
    const physical = new Map(Object.keys(containers).map((id) => [id, []]));
    for (const [id, container] of Object.entries(containers)) {
      if (container.parent && children.has(container.parent)) children.get(container.parent).push(id);
    }
    children.forEach((ids) => ids.sort());
    const byId = new Map(graphNodes.map((node) => [node.id, node]));
    const frameIds = new Set(Object.keys(containers));
    const physicalParent = new Map();
    for (const edge of graph?.edges || []) {
      if (frameIds.has(edge.source) && !physicalParent.has(edge.target)) {
        physicalParent.set(edge.target, edge.source);
      }
    }
    for (const node of graphNodes) {
      if (node.kind === "physical_child" || node.kind === "module_target" || node.kind === "folder") {
        const parent = physicalParent.get(node.id);
        if (parent && physical.has(parent)) physical.get(parent).push(node.id);
      }
    }
    physical.forEach((ids) => ids.sort());

    const rankNodes = graphNodes.filter((node) => node.kind === "component");
    const visibleRanks = [...new Set(rankNodes
      .map((node) => node.dependency_rank)
      .filter((rank) => rank !== null))].sort((left, right) => left - right);
    const rowByRank = new Map(visibleRanks.map((rank, index) => [rank, index]));
    const residualRow = visibleRanks.length;
    const step = CARD.w + GAP;
    const availableColumns = Math.max(1, Math.floor((canvas.clientWidth - 64 + GAP) / step));
    const maxColumns = targetPath.length > 0 ? Math.max(2, availableColumns) : availableColumns;
    const rowFor = (node) => node.kind === "component"
      ? node.dependency_rank === null ? residualRow : rowByRank.get(node.dependency_rank)
      : residualRow + 1;
    const itemsFor = (id) => [
      ...(containers[id].members || []).filter((member) => byId.has(member)),
      ...physical.get(id).filter((member) => byId.has(member)),
    ];
    const laneItems = new Map(Object.keys(containers).sort().map((id) => [id, itemsFor(id)]));
    const containerMembers = new Set([...laneItems.values()].flat());
    const unplacedNodes = rankNodes.filter((node) => !containerMembers.has(node.id));
    laneItems.set("@unplaced", unplacedNodes.map((node) => node.id));
    const inventory = graphNodes.filter((node) =>
      !frameIds.has(node.id) && node.id !== graph?.owner
      && !containerMembers.has(node.id) && !rankNodes.includes(node),
    ).sort((left, right) => left.id.localeCompare(right.id));
    laneItems.set("@inventory", inventory.map((node) => node.id));
    const groupedRows = new Map();
    for (const [lane, identifiers] of laneItems) {
      const grouped = new Map();
      identifiers.forEach((identifier) => {
        const row = rowFor(byId.get(identifier));
        if (!grouped.has(row)) grouped.set(row, []);
        grouped.get(row).push(identifier);
      });
      for (const ids of grouped.values()) ids.sort();
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
        const count = Math.ceil((groupedRows.get(lane).get(rankRow)?.length || 0) / maxColumns);
        rowHeight = Math.max(rowHeight, count);
      }
      rowStarts.set(rankRow, nextRow);
      rowHeights.set(rankRow, Math.max(1, rowHeight));
      nextRow += rowHeights.get(rankRow);
    });
    const rowOffset = (row, ids) =>
      targetPath.length > 0 && ids.length === 1 ? row % 2 : 0;
    const rowsFor = (id) => {
      const rows = new Map();
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
        return node.kind === "component" && node.dependency_rank === null;
      }) ? depth : 0,
      ...children.get(id).map((child) => residualFrameDepth(child, depth + 1)),
    );
    const residualRowStart = rowStarts.get(residualRow);
    const residualFrameAllowance = Object.keys(containers)
      .filter((id) => !containers[id].parent)
      .reduce((depth, id) => Math.max(depth, residualFrameDepth(id)), 0)
      * TARGET_FRAME_HEADER_ALLOWANCE;
    const hasResidualComponents = rankNodes.some((node) => node.dependency_rank === null);
    const captionBand = TARGET_RESIDUAL_GAP
      + (hasResidualComponents ? residualFrameAllowance : 0);
    const rowY = (row) => row * (CARD.h + 34)
      + (row >= residualRowStart ? captionBand : 0);
    const laneWidth = (id) => {
      const rows = rowsFor(id);
      const columns = Math.max(1, ...[...rows].map(([row, ids]) =>
        ids.length + rowOffset(row, ids)));
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
      const rowWidth = Math.max(1, ...[...rows].map(([row, ids]) =>
        ids.length + rowOffset(row, ids)));
      rows.forEach((items, row) => items.forEach((identifier, index) => {
        if (!placed.has(identifier)) {
          nextPositions[identifier] = {
            x: x + (index + rowOffset(row, items)) * step,
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
        ...itemsFor(id).map((identifier) => nextPositions[identifier]),
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
    let unplacedWidth = 1;
    rowsFor("@unplaced").forEach((nodes, row) => {
        const offset = rowOffset(row, nodes);
        unplacedWidth = Math.max(unplacedWidth, nodes.length + offset);
        nodes.forEach((identifier, column) => {
          nextPositions[identifier] = {
            x: x + (column + offset) * step,
            y: y + rowY(row),
          };
          placed.add(identifier);
        });
    });
    x += unplacedWidth * step;
    rowsFor("@inventory").forEach((nodes, row) => {
      const offset = rowOffset(row, nodes);
      nodes.forEach((identifier, index) => {
        nextPositions[identifier] = {
          x: x + (index + offset) * step,
          y: y + rowY(row),
        };
      });
    });
    if (graph?.owner && !nextPositions[graph.owner]) {
      nextPositions[graph.owner] = { x: 0, y: 0 };
    }

    const same = Object.keys(positions).length === Object.keys(nextPositions).length
      && Object.entries(nextPositions).every(([id, position]) =>
        positions[id]?.x === position.x && positions[id]?.y === position.y);
    const captionY = hasResidualComponents && residualRowStart !== undefined
      ? residualRowStart * (CARD.h + 34) + 4 : null;
    return { positions: same ? positions : nextPositions, frameBounds, captionY };
  }

  function targetGraphFor(current) {
    const diagrams = DATA.explorers.target_diagrams;
    const graph = current
      ? diagrams.nested[current.id]
      : diagrams.root;
    if (!current || !graph) return graph;
    const sources = [diagrams.root, ...Object.values(diagrams.nested)];
    const members = [...new Set(sources.flatMap((source) =>
      source.containers?.[current.id]?.members || []))];
    if (!members.length) return graph;
    const available = new Map();
    sources.forEach((source) => source.nodes.forEach((node) => {
      if (members.includes(node.id) && !available.has(node.id)) available.set(node.id, node);
    }));
    const nodes = [...graph.nodes];
    const present = new Set(nodes.map((node) => node.id));
    members.forEach((id) => {
      const node = available.get(id);
      if (node && !present.has(id)) nodes.push(node);
    });
    const containers = {
      ...graph.containers,
      [current.id]: {
        ...graph.containers[current.id],
        members,
      },
    };
    return { ...graph, nodes, containers };
  }

  function renderTargetDiagram() {
    const focusedNode = document.activeElement.closest("[data-target-node]")?.dataset.targetNode;
    const focusedEdge = document.activeElement.closest("[data-target-edge]")?.dataset.targetEdge;
    const current = targetNode(targetPath.at(-1));
    const graph = targetGraphFor(current);
    const graphNodes = graph?.nodes || [];
    const cardMetrics = targetCardMetrics(graphNodes);
    const layout = targetLayout(graph, graphNodes);
    positions = layout.positions;
    emptyLayer.textContent = "";
    frameLayer.textContent = "";
    edgeLayer.textContent = "";
    chipLayer.textContent = "";
    nodeLayer.textContent = "";

    const containers = graph?.containers || {};
    Object.entries(containers).forEach(([id, container]) => {
      const bounds = layout.frameBounds[id];
      const record = targetNode(id);
      if (!bounds || !record) return;
      const group = el("g", {
        class: `node target-node target-container${targetSelection === id ? " selected" : ""}`,
        tabindex: "0",
        role: "button",
        "aria-label": `Select Package layout ${compactFrameName(container.scope || record.label, bounds.right - bounds.left - 28)}. Canonical scope ${container.scope || record.label}`,
        "data-target-node": id,
        "data-label": record.label,
        "aria-pressed": String(targetSelection === id),
        "data-target-container": id,
        "data-target-container-open": id,
      });
      const backplate = el("g", { class: "target-frame-backplate", "aria-hidden": "true" });
      backplate.appendChild(el("rect", {
        class: "target-frame",
        x: String(bounds.left),
        y: String(bounds.top),
        width: String(bounds.right - bounds.left),
        height: String(bounds.bottom - bounds.top),
        rx: "8",
      }));
      nodeLayer.appendChild(backplate);
      group.appendChild(el("rect", {
        class: "target-frame-header-hit",
        x: String(bounds.left),
        y: String(bounds.top),
        width: String(bounds.right - bounds.left),
        height: String(TARGET_FRAME_HEADER_ALLOWANCE),
        rx: "8",
      }));
      const fullScope = container.scope || record.label;
      const name = compactFrameName(fullScope, bounds.right - bounds.left - 28);
      frameHeaderText(group, "Package layout", name, bounds.left + 14, bounds.top + 37);
      const tooltip = el("title");
      tooltip.textContent = `Package layout ${name}. Canonical scope ${fullScope}. ${container.members.length} direct component${container.members.length === 1 ? "" : "s"}. Open frame.`;
      group.appendChild(tooltip);
      const select = () => {
        projectionContext = null;
        projectionReturnContext = null;
        selectSubject(record);
        targetSelection = id;
        render();
      };
      const enter = () => {
        if (graph?.owner !== id && (record.children || []).length) {
          invalidateOtherViewStates();
          selectSubject(record);
          targetSelection = id;
          rememberNavigationState();
          targetPath.push(id);
          targetSelection = null;
          render();
          focusCurrentLevel();
        } else select();
      };
      group.addEventListener("click", (event) => {
        if (event.detail > 1) return;
        select();
      });
      group.addEventListener("dblclick", (event) => {
        event.preventDefault();
        enter();
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          enter();
        } else if (event.key === " ") {
          event.preventDefault();
          select();
        }
      });
      nodeLayer.appendChild(group);
    });

    const edges = graph?.edges || [];
    const lanes = groupBy(edges, laneKey);
    lanes.forEach((bucket) => bucket.sort((a, b) =>
      positions[a.source].x - positions[b.source].x || positions[a.target].x - positions[b.target].x));
    // Draw requirements last: their direct component links remain pointer-accessible
    // where they cross the lower-contrast containment/ownership context edges.
    const targetEdgePriority = {
      navigation_grouping: 0, allowed_child: 1, contains: 2, owns_package: 3, requires: 4,
    };
    [...edges].sort((a, b) => targetEdgePriority[a.kind] - targetEdgePriority[b.kind]).forEach((edge) => {
      const route = routeFor(
        edge, 0, 0, 1, 1, laneOffsetFor(edge, lanes),
        protectedFrameHeaders(layout.frameBounds), layout.frameBounds,
      );
      const path = route.d;
      const declaration = edge.declaration || `${edge.source}>${edge.target}`;
      const routeWarning = route.routingWarning
        ? " Renderer layout warning: no clear route around a frame header; architectural status is unchanged."
        : "";
      const group = el("g", {
        class: `edge target-edge ${edge.kind}${targetSelection === declaration ? " selected" : ""}`,
        tabindex: "0",
        role: "button",
        "aria-label": `${edge.kind}: ${edge.label}.${routeWarning}`,
        "aria-pressed": String(targetSelection === declaration),
        "data-target-edge": declaration,
        ...(route.routingWarning ? { "data-route-warning": "header-overlap" } : {}),
      });
      const line = el("path", { class: "line", d: path, "stroke-width": "2" });
      const title = el("title");
      title.textContent = `${edge.kind}: ${edge.label}.${routeWarning}`;
      line.appendChild(title);
      group.appendChild(line);
      group.appendChild(el("path", {
        class: "hit target-hit", d: path, "aria-hidden": "true", "pointer-events": "stroke",
      }));
      const inspect = () => {
        invalidateOtherViewStates();
        projectionContext = null;
        projectionReturnContext = null;
        targetSelection = edge.declaration || null;
        selectedSubject = null;
        render();
      };
      group.addEventListener("click", inspect);
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          inspect();
        }
      });
      edgeLayer.appendChild(group);
    });

    graphNodes.forEach((node) => {
      if (containers[node.id]) return;
      const position = positions[node.id];
      if (!position) return;
      const type = node.kind === "component" ? "component"
        : node.kind === "requires" ? "requires"
          : node.kind === "root_layout" ? "layout"
            : node.kind === "physical_child" ? "physical"
              : node.kind === "module_target" ? "module"
                : node.kind === "folder" ? "folder"
                  : node.kind === "category" ? "group" : "package";
      const group = el("g", {
        class: `node target-node ${type}${targetSelection === node.id ? " selected" : ""}`,
        transform: `translate(${position.x},${position.y})`,
        tabindex: "0",
        role: "button",
        "aria-label": `Select ${type}: ${node.label}`,
        "data-label": node.label,
        "data-target-node": node.id,
        "aria-pressed": String(targetSelection === node.id),
        ...(node.kind === "component" ? { "data-placement-status": node.placement?.status || "unmapped" } : {}),
      });
      group.appendChild(el("rect", {
        class: "card target-card", width: String(CARD.w), height: String(CARD.h), rx: "8",
      }));
      const kind = el("text", { class: "stereotype target-kind", x: "16", y: "19" });
      kind.textContent = type === "component" ? "COMPONENT"
        : type === "requires" ? "REQUIRES"
          : type === "layout" ? "ROOT LAYOUT"
            : type === "physical" ? "ALLOWED CHILD"
              : type === "module" ? "MODULE"
                : type === "folder" ? "FOLDER"
                  : type === "group" ? "GROUP" : "PACKAGE SCOPE";
      group.appendChild(kind);
      const metric = cardMetrics.get(node.id);
      appendWrappedText(group, node.label, {
        class: "label target-label", x: "16", y: "47",
      }, CARD.w - 32, `600 15px ${sansFontFamily}`, 18);
      const targetRecord = targetNode(node.id);
      const children = targetRecord?.children || [];
      const components = children.filter((child) => child.kind === "component").length;
      const allowed = children.filter((child) => child.kind === "physical_child").length;
      const countText = components
        ? `${components} component${components === 1 ? "" : "s"}`
        : allowed
          ? `${allowed} allowed child${allowed === 1 ? "" : "ren"}`
          : children.length ? "Details" : "Declared leaf";
      const responsibilities = (targetRecord?.details || []).filter((detail) =>
        detail.label === "Responsibility" && !detail.missing && detail.value);
      let nextY = metric?.responsibilityY || 72;
      responsibilities.forEach((detail) => {
        const lines = appendWrappedText(group, String(detail.value), {
          class: "meta target-responsibility", x: "16", y: String(nextY),
        }, CARD.w - 32, `13px ${sansFontFamily}`, 15);
        nextY += lines.length * 15 + 2;
      });
      if (!responsibilities.length && metric?.missingLines.length) {
        const lines = appendWrappedText(group, "No declared responsibility.", {
          class: "meta target-responsibility", x: "16", y: String(nextY),
        }, CARD.w - 32, `13px ${sansFontFamily}`, 15);
        nextY += lines.length * 15 + 2;
      }
      if (!responsibilities.length) appendWrappedText(group, countText, {
        class: "meta target-meta", x: "16", y: String(metric?.countY || 72),
      }, CARD.w - 32, "12px monospace", 15);
      const title = el("title");
      title.textContent = `${type}: ${node.label}${responsibilities.length
        ? " — " + responsibilities.map((item) => item.value).join(" ")
        : metric?.missingLines.length ? " — No declared responsibility." : ""}`;
      group.appendChild(title);
      const open = () => {
        if (graph?.owner === node.id) {
          selectSubject(targetRecord);
          targetSelection = node.id;
        } else if ((targetRecord?.children || []).length) {
          invalidateOtherViewStates();
          selectSubject(targetRecord);
          targetSelection = node.id;
          rememberNavigationState();
          targetPath.push(node.id);
          targetSelection = null;
        } else {
          selectSubject(targetRecord);
          targetSelection = node.id;
        }
        render();
        if (targetPath.at(-1) === node.id) focusCurrentLevel();
      };
      group.addEventListener("click", (event) => {
        if (event.detail > 1) return;
        selectSubject(targetRecord);
        targetSelection = node.id;
        render();
      });
      group.addEventListener("dblclick", (event) => {
        event.preventDefault();
        open();
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          open();
        } else if (event.key === " ") {
          event.preventDefault();
          selectSubject(targetRecord);
          targetSelection = node.id;
          render();
        }
      });
      nodeLayer.appendChild(group);
    });

    if (layout.captionY !== null) {
      const warning = el("text", {
        class: "target-cycle-warning",
        x: String(Math.min(0, ...Object.values(layout.frameBounds).map((bounds) => bounds.left))),
        y: String(layout.captionY),
      });
      warning.textContent = "Dependency order unresolved: cycle or dependency on a cycle.";
      emptyLayer.appendChild(warning);
    }

    legend.textContent = "";
    for (const [kind, label] of [
      ["navigation_grouping", "Navigation grouping by package scope"],
      ["allowed_child", "Layout allows child"],
      ["owns_package", "Component owns package scope"],
      ["contains", "Declared containment"],
      ["requires", "Declared requirement"],
    ]) {
      const item = document.createElement("span");
      item.className = "flow-legend-item";
      item.appendChild(el("span", { class: `target-legend-swatch ${kind}` }));
      const text = document.createElement("span");
      text.textContent = label;
      item.appendChild(text);
      legend.appendChild(item);
    }
    const scopeHint = document.createElement("span");
    scopeHint.className = "flow-legend-hint";
    scopeHint.dataset.scopeCount = `${graphNodes.length}/${graphNodes.length}`;
    scopeHint.textContent = `${graphNodes.length} of ${graphNodes.length} items shown in this scope · scroll to see all`;
    legend.appendChild(scopeHint);
    inspector.hidden = !targetDetailsOpen;
    renderTargetInspector(graph);
    sizeDiagram();
    const focusTarget = focusedEdge
      ? edgeLayer.querySelector(`[data-target-edge="${CSS.escape(focusedEdge)}"]`)
      : nodeLayer.querySelector(`[data-target-node="${CSS.escape(focusedNode || "")}"]`);
    if (focusTarget) focusTarget.focus({ preventScroll: true });
    updateOpenSelected();
  }

  function render() {
    renderSelectedResponsibility();
    updateNavigation();
    const scope = fullLevel();
    const maximum = level().edges.reduce((acc, edge) => Math.max(acc, weight(edge)), 0);
    normalizeThreshold(maximum);
    if (focusLabel && !scope.components.some((card) => card.label === focusLabel)) focusLabel = null;
    focusInput.innerHTML = `<option value="">All components and groups</option>` + scope.components.map((card) =>
      `<option value="${esc(card.label)}">${esc(card.display || card.label)}</option>`).join("");
    focusInput.value = focusLabel || "";
    focusInput.disabled = !scope.components.length;
    root.dataset.view = viewMode;
    flowHeading.textContent = "Architecture explorer";
    viewButtons.forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.flowView === viewMode)));
    alternative.hidden = viewMode === "diagram" || viewMode === "target";
    responsibilities.hidden = false;
    inspector.hidden = !targetDetailsOpen;
    updateOpenSelected();
    // Keep the shared toolbar's measured height stable while this Diagram-only status
    // is visually hidden in the other views.
    filterStatus.textContent = activeFilterSummary("diagram");
    if (viewMode === "target") {
      renderResponsibilities();
      renderTargetDiagram();
      return;
    }
    if (viewMode !== "diagram") {
      renderAlternative();
      return;
    }
    // render() replaces every card and edge, which would otherwise silently drop keyboard focus.
    const focused = capturedFocus();
    emptyLayer.textContent = "";
    frameLayer.textContent = "";
    if (!level().components.length) {
      edgeLayer.textContent = "";
      nodeLayer.textContent = "";
      chipLayer.textContent = "";
      const text = el("text", { x: "0", y: "0", fill: "var(--ck-muted)" });
      text.textContent = opened
        ? `${opened.module || opened.component} holds nothing to show.`
        : "This observation declares no components.";
      emptyLayer.appendChild(text);
      updateEdgeCount(visibleEdges().length, fullLevel().edges.length);
      sizeDiagram();
      renderInspector([]);
      return;
    }
    const modulesMeta = (card) =>
      `${card.modules.length} module${card.modules.length === 1 ? "" : "s"} · ${
        card.public === null ? "no public" : `public ${card.public.length}`
      }`;
    const diagramMeta = (component) => opened
      ? opened.module
        ? `${component.kind}${component.members.length ? ` · ${component.members.length} method${component.members.length === 1 ? "" : "s"}` : ""}${component.public === null ? "" : " · used outside"}`
        : component.folder
          ? `${component.modules.length} modules · ${component.import_sites} import sites`
          : component.modules && component.modules.length > 1
            ? modulesMeta(component)
            : component.opensModule
              ? (component.public === null ? "internal part" : "provided part")
              : component.public === null
                ? "internal part"
                : "provided part"
      : component.navigation_only
        ? `${component.modules.length} modules · navigation only`
        : component.library ? `${component.import_sites} import sites` : modulesMeta(component);
    const diagramMetrics = new Map();
    let diagramHeight = 92;
    level().components.forEach((component) => {
      const lines = wrapText(component.display || component.label, 156, `600 14px ${sansFontFamily}`);
      const metaLines = wrapText(diagramMeta(component), CARD.w - 32, `12px ${monoFontFamily}`);
      const metaY = 42 + lines.length * 18;
      const responsibilityLines = diagramResponsibilities(component)
        .reduce((count, text) => count + wrapText(text, CARD.w - 32, `13px ${sansFontFamily}`).length, 0);
      const responsibilityY = metaY + metaLines.length * 14 + 6;
      diagramMetrics.set(component.label, { lines, metaLines, metaY, responsibilityY });
      diagramHeight = Math.max(diagramHeight, responsibilityLines
        ? responsibilityY + responsibilityLines * 15 + 10 : metaY + metaLines.length * 14 + 10);
    });
    CARD.h = diagramHeight;
    layout();
    const physicalFrames = diagramPhysicalFrames(fullLevel());
    const frameBounds = layoutDiagramFrames(physicalFrames, level().components);
    renderDiagramFrames(physicalFrames, frameBounds);
    const visible = visibleEdges();
    updateEdgeCount(visible.length, fullLevel().edges.length);
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
          protectedFrameHeaders(frameBounds),
          frameBounds,
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
      const routeWarning = r.routingWarning
        ? " Renderer layout warning: no clear route around a frame header; architectural status is unchanged."
        : "";
      title.textContent = `${r.edge.source} uses ${r.edge.target}; ${edgeCountLabel(r.edge)}; ${r.edge.state}. ${contractText} ${ruleText}${(r.edge.sites || []).length ? ` Example: ${r.edge.sites.join(", ")}` : ""}${routeWarning}`;
      const select = () => {
        selected = { type: "edge", key: edgeKey(r.edge) };
        render();
      };
      r.select = select;
      const hit = el(
        "path",
        {
          class: "hit",
          d: r.d,
          tabindex: "0",
          role: "button",
          "aria-label": `${r.edge.source} to ${r.edge.target}, ${edgeCountLabel(r.edge)}.${routeWarning}`,
          "data-key": edgeKey(r.edge),
          ...(r.routingWarning ? { "data-route-warning": "header-overlap" } : {}),
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
    const frameHeaderBoxes = protectedFrameHeaders(frameBounds).map((header) => ({
      x: header.left - 4,
      y: header.top - 4,
      w: header.right - header.left + 8,
      h: header.bottom - header.top + 8,
    }));
    const protectedBoxes = [...cardBoxes, ...frameHeaderBoxes];
    const placed = [];
    const fractions = [0.5, 0.35, 0.65, 0.2, 0.8, 0.12, 0.88];
    // Keep rule ids visible first, then make placement independent of input edge order.
    const byPriority = [...routed].sort((a, b) =>
      Number(b.edge.state === "violation") - Number(a.edge.state === "violation")
        || edgeKey(a.edge).localeCompare(edgeKey(b.edge)));
    const gutter = [];
    byPriority.forEach((r) => {
      const extra = r.edge.rule_ids.length > 1 ? ` +${r.edge.rule_ids.length - 1}` : "";
      const label = r.edge.rule_ids.length ? `${r.edge.rule_ids[0]}${extra}` : String(weight(r.edge));
      const text = el("text", { "text-anchor": "middle", "dominant-baseline": "central" });
      text.textContent = label;
      const rect = el("rect", { rx: "3", height: "18" });
      const fullRuleIds = r.edge.rule_ids.length ? ` Rules: ${r.edge.rule_ids.join(", ")}.` : "";
      const group = el("g", {
        class: `chip ${r.edge.state}${related(r.edge) ? "" : " dim"}`,
        tabindex: "0",
        role: "button",
        cursor: "pointer",
        "aria-pressed": String(selected?.type === "edge" && selected.key === edgeKey(r.edge)),
        "aria-label": `${r.edge.source} to ${r.edge.target}, ${edgeCountLabel(r.edge)}, `
          + `${r.edge.state}; ${label}.${fullRuleIds} Select for details.`,
        "data-key": edgeKey(r.edge),
      }, rect, text);
      chipLayer.appendChild(group);
      group.addEventListener("pointerdown", (event) => event.stopPropagation());
      group.addEventListener("click", (event) => {
        event.stopPropagation();
        r.select();
      });
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          r.select();
        }
      });
      const width = Math.max(24, text.getComputedTextLength() + 12);
      rect.setAttribute("x", String(-width / 2));
      rect.setAttribute("y", "-9");
      rect.setAttribute("width", String(width));
      const labelBounds = group.getBBox();
      const length = r.node.getTotalLength();
      let best = null;
      for (const fraction of fractions) {
        const point = r.node.getPointAtLength(length * fraction);
        const box = {
          x: point.x + labelBounds.x - 3,
          y: point.y + labelBounds.y - 3,
          w: labelBounds.width + 6,
          h: labelBounds.height + 6,
        };
        if (![...protectedBoxes, ...placed].some((other) => overlaps(box, other))) {
          best = { point, box };
          break;
        }
      }
      if (!best) {
        gutter.push({ group, labelBounds, r, text, rect, label });
        return;
      }
      placed.push(best.box);
      group.setAttribute("transform", `translate(${best.point.x},${best.point.y})`);
    });
    if (gutter.length) {
      gutter.forEach(({ group, r, text, rect, label }, index) => {
        text.textContent = `${r.edge.source} → ${r.edge.target} · ${label}`;
        const width = Math.max(24, text.getComputedTextLength() + 12);
        rect.setAttribute("x", String(-width / 2));
        rect.setAttribute("y", "-9");
        rect.setAttribute("width", String(width));
        gutter[index].labelBounds = group.getBBox();
      });
      const right = Math.max(
        0,
        ...cardBoxes.map((box) => box.x + box.w),
        ...Object.values(frameBounds).map((frame) => frame.right),
        ...placed.map((box) => box.x + box.w),
        ...routed.map((r) => {
          const bounds = r.node.getBBox();
          return bounds.x + bounds.width;
        }),
      );
      const left = right + GAP;
      let top = Math.min(0, ...cardBoxes.map((box) => box.y),
        ...Object.values(frameBounds).map((frame) => frame.top));
      gutter.forEach(({ group, labelBounds }) => {
        const box = {
          x: left,
          y: top,
          w: labelBounds.width + 6,
          h: labelBounds.height + 6,
        };
        group.setAttribute(
          "transform",
          `translate(${left - labelBounds.x + 3},${top - labelBounds.y + 3})`,
        );
        placed.push(box);
        top += box.h + GAP;
      });
    }

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
      const metric = diagramMetrics.get(component.label);
      const label = createWrappedText(component.display || component.label, {
        class: "label", x: "16", y: "37",
      }, 156, `600 14px ${sansFontFamily}`, 18);
      const stereotype = el("text", { class: "stereotype", x: "16", y: "17" });
      const declaredInside = Boolean(level().declaredInside);
      const declaredComponent = declaredInside && component.declared_inside_component;
      stereotype.textContent = component.navigation_only ? "«unassigned»" : component.library ? "«library»" : (!opened || declaredComponent) ? "«component»" : opened.module ? "«code»" : component.folder ? "«package»" : "«module»";
      const meta = createWrappedText(diagramMeta(component), {
        class: "meta", x: "16", y: String(metric.metaY),
      }, CARD.w - 32, `12px ${monoFontFamily}`, 14);
      let responsibilityY = metric.responsibilityY;
      const responsibilityText = diagramResponsibilities(component);
      const responsibilityNodes = responsibilityText.map((text) => {
        const node = createWrappedText(text, {
          class: "meta diagram-responsibility", x: "16", y: String(responsibilityY),
        }, CARD.w - 32, `13px ${sansFontFamily}`, 15);
        responsibilityY += wrapText(text, CARD.w - 32, `13px ${sansFontFamily}`).length * 15;
        return node;
      });
      const umlIcon = !component.library && !component.navigation_only && (!opened || declaredComponent || (opened.inside === undefined && component.modules && component.modules.length > 1))
        ? el("g", { class: "uml-icon" },
          el("rect", { x: "175", y: "12", width: "15", height: "17" }),
          el("rect", { x: "170", y: "16", width: "7", height: "4" }),
          el("rect", { x: "170", y: "23", width: "7", height: "4" })) : null;
      const provided = (!opened || declaredComponent) && !component.navigation_only && component.public !== null && component.public.length
        ? el("g", { class: "uml-provided" },
          el("line", { x1: "200", y1: "45", x2: "213", y2: "45" }),
          el("circle", { cx: "219", cy: "45", r: "6" })) : null;
      const required = (!opened || declaredComponent) && !component.navigation_only && component.requires && component.requires.length
        ? el("g", { class: "uml-required" },
          el("line", { x1: "0", y1: "45", x2: "-9", y2: "45" }),
          el("path", { d: "M-9,37 Q-18,45 -9,53" })) : null;
      const tooltip = el("title");
      tooltip.textContent = component.navigation_only
        ? `${component.label}: modules without a unique declared owner. Navigation only; no component boundary or contract verdict is implied. Select to inspect the module inventory.`
        : component.library
        ? `${component.display}: external library scope under ${scopeRules(component).map((rule) => rule.rule_id).join(", ")}.`
        : !opened || declaredComponent
        ? `${component.label}: ${component.modules.length} modules; ${component.public === null ? "no interface boundary declared" : `${component.public.length} provided entries`}; ${(component.requires || []).length} required components. ${responsibilityText.join(" ")} Select for details; Enter or Open selected to open.`
        : `${component.label}: ${component.folder ? "physical package, not a declared component" : "module"}; ${component.import_sites || 0} import sites touching it.`;
      const group = el(
        "g",
        {
          class: `node${isSelected ? " selected" : ""}${dim ? " dim" : ""}`,
          transform: `translate(${pos.x},${pos.y})`,
          tabindex: "0",
          role: "button",
          "aria-pressed": String(Boolean(isSelected)),
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
        ...responsibilityNodes,
        ...(umlIcon ? [umlIcon] : []),
        ...(provided ? [provided] : []),
        ...(required ? [required] : []),
        tooltip,
      );
      // A card's own click never fires for a mouse: its pointerdown captures the pointer on the
      // svg, and the capture retargets the click there too. Mouse taps therefore arrive through
      // endPointer below, and every path funnels into selectCard so all three behave alike.
      group.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          enter(component.label);
        } else if (event.key === " ") {
          event.preventDefault();
          selectCard(component.label);
        }
      });
      group.addEventListener("dblclick", (event) => {
        event.preventDefault();
        enter(component.label);
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
    sizeDiagram();
    updateOpenSelected();
  }

  function splitMap(items, x, y, width, height) {
    if (items.length === 1) return [{ item: items[0], x, y, width, height }];
    const total = items.reduce((sum, item) => sum + item.area, 0);
    let first = 0;
    let cut = 0;
    for (let index = 0; index < items.length - 1; index += 1) {
      first += items[index].area;
      cut = index + 1;
      if (first >= total / 2) break;
    }
    const share = first / total;
    return width >= height
      ? [...splitMap(items.slice(0, cut), x, y, width * share, height),
        ...splitMap(items.slice(cut), x + width * share, y, width * (1 - share), height)]
      : [...splitMap(items.slice(0, cut), x, y, width, height * share),
        ...splitMap(items.slice(cut), x, y + height * share, width, height * (1 - share))];
  }

  function renderStructure(view) {
    const cards = view.components.filter((card) => !card.library);
    const count = (card) => opened?.module ? 1 + (card.members || []).length : card.modules.length;
    const area = (card) => Math.max(1, count(card));
    const sorted = [...cards].sort((a, b) => area(b) - area(a) || a.label.localeCompare(b.label));
    const mapped = sorted.slice(0, 20).map((card) => ({ card, area: area(card), count: count(card) }));
    const rectangles = mapped.length ? splitMap(mapped, 0, 0, 100, 100) : [];
    const unit = opened?.module ? "definitions and members" : "observed modules";
    const tiles = rectangles.map(({ item, x, y, width, height }) => {
      const card = item.card;
      const label = card.display || card.label;
      return `<button type="button" class="${card.folder ? "folder" : "module"}"
        data-flow-card="${esc(card.label)}" aria-label="Open ${esc(card.label)}"
        aria-pressed="${selected?.type === "node" && selected.label === card.label}"
        style="left:${x}%;top:${y}%;width:${width}%;height:${height}%">
        <b>${esc(label)}</b><small>${item.count} ${unit}</small></button>`;
    }).join("");
    const all = sorted.map((card) => `<button type="button" data-flow-card="${esc(card.label)}"
      aria-pressed="${selected?.type === "node" && selected.label === card.label}">
      <span><code>${esc(card.display || card.label)}</code></span>
      <small>${count(card)} ${unit}</small></button>`).join("");
    const libraries = view.components.filter((card) => card.library).map((card) =>
      `<button type="button" data-flow-card="${esc(card.label)}"><span>${esc(card.display)}</span>
      <small>external library</small></button>`).join("");
    alternative.innerHTML = `<h2>Physical structure</h2>
      <p>Tile area counts ${unit}, not code quality.
      Select a tile to open it; the full list also includes small entries.</p>
      ${tiles ? `<div class="flow-map" role="group" aria-label="Package and module map">${tiles}</div>`
        : "<p>No structure recorded at this level.</p>"}
      <p>${mapped.length} of ${cards.length} entries in the map.</p>
      <div class="flow-item-list">${all}${libraries}</div>`;
  }

  function renderReview(view) {
    const display = new Map(view.components.map((card) => [card.label, card.display || card.label]));
    const scores = new Map(view.components.map((card) => [card.label, 0]));
    view.edges.forEach((edge) => {
      scores.set(edge.source, (scores.get(edge.source) || 0) + weight(edge));
      scores.set(edge.target, (scores.get(edge.target) || 0) + weight(edge));
    });
    const cards = [...view.components].sort((a, b) =>
      (scores.get(b.label) || 0) - (scores.get(a.label) || 0) || a.label.localeCompare(b.label));
    const shown = cards.slice(0, 12);
    const edges = new Map(view.edges.map((edge) => [edgeKey(edge), edge]));
    const head = shown.map((card) => `<th scope="col" title="${esc(card.label)}">${esc(card.display || card.label)}</th>`).join("");
    const rows = shown.map((source) => `<tr><th scope="row" title="${esc(source.label)}">${esc(source.display || source.label)}</th>${shown.map((target) => {
      const edge = edges.get(`${source.label}>${target.label}`);
      if (!edge) return "<td>·</td>";
      return `<td><button type="button" data-flow-edge="${esc(edgeKey(edge))}"
        data-state="${esc(edge.state)}" aria-label="${esc(source.label)} uses ${esc(target.label)}:
        ${esc(edgeCountLabel(edge))}, ${esc(edge.state)}"
        aria-pressed="${selected?.type === "edge" && selected.key === edgeKey(edge)}">
        ${edge.kind === "symbol_use" ? "•" : edge.import_sites}</button></td>`;
    }).join("")}</tr>`).join("");
    const urgency = { violation: 0, undecided: 1, conforms: 2, observed: 2 };
    const ordered = [...view.edges].sort((a, b) =>
      (urgency[a.state] ?? 3) - (urgency[b.state] ?? 3) ||
      weight(b) - weight(a) || edgeKey(a).localeCompare(edgeKey(b)));
    const flagged = ordered.filter((edge) => edge.state === "violation" || edge.state === "undecided");
    const priority = [
      ...flagged,
      ...ordered.filter((edge) => !flagged.includes(edge)).slice(0, Math.max(0, 12 - flagged.length)),
    ];
    const remaining = ordered.filter((edge) => !priority.includes(edge));
    const edgeButton = (edge) => `<button type="button" data-flow-edge="${esc(edgeKey(edge))}"
      aria-pressed="${selected?.type === "edge" && selected.key === edgeKey(edge)}"
      title="${esc(edge.source)} → ${esc(edge.target)}${edge.sites?.length ? ` · ${esc(edge.sites.join(", "))}` : ""}">
      <span>${esc(display.get(edge.source) || edge.source)} → ${esc(display.get(edge.target) || edge.target)}${edge.rule_ids.length ? ` · ${esc(edge.rule_ids.join(", "))}` : ""}</span>
      <small>${esc(edgeCountLabel(edge))}${edge.names?.length ? ` · ${edge.names.length} names` : ""} · ${esc(edge.state)}</small></button>`;
    const broken = view.edges.filter((edge) => edge.state === "violation").length;
    const undecided = view.edges.filter((edge) => edge.state === "undecided").length;
    const nodeButtons = cards.map((card) => `<button type="button" data-flow-card="${esc(card.label)}">
      <span>${esc(card.display || card.label)}</span><small>${card.folder ? "package" : card.library ? "library" : "open"}</small>
      </button>`).join("");
    alternative.innerHTML = `<h2>Connections to inspect</h2>
      <p>${view.edges.length} observed connections at this level:
      ${broken} break declared rules, ${undecided} need a decision. A clear rule check does not
      establish that the public API is well designed.</p>
      <h3>Connections to inspect</h3>
      <div class="flow-item-list">${priority.map(edgeButton).join("") || "<p>No observed connections.</p>"}</div>
      ${remaining.length ? `<details><summary>Other connections · ${remaining.length}</summary>
        <div class="flow-item-list">${remaining.map(edgeButton).join("")}</div></details>` : ""}
      <details class="flow-review-matrix"><summary>Dependency matrix · ${shown.length} of ${cards.length} entries</summary>
        <p>Row uses column. Numbers count import sites; • marks a symbol-use edge; · means no observed connection.</p>
        ${shown.length ? `<div class="flow-matrix-wrap"><table class="flow-matrix"><thead>
          <tr><th scope="col">uses →</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>`
          : "<p>No components or modules recorded at this level.</p>"}</details>
      <details><summary>Open an entry</summary><div class="flow-item-list">${nodeButtons}</div></details>`;
  }

  function renderExplorer() {
    const roots = DATA.explorers?.[viewMode] || [];
    const path = [];
    let entries = roots;
    for (const id of projectionPath) {
      const node = entries.find((item) => item.id === id);
      if (!node) {
        projectionPath = [];
        projectionSelection = null;
        entries = roots;
        path.length = 0;
        break;
      }
      path.push(node);
      entries = node.children || [];
    }
    const current = path.at(-1);
    const title = current?.label || ({ actual: "Observed modules", target: "Declared target", diff: "Differences" })[viewMode];
    const details = (node) => (node.details || []).map((item) =>
      `<dt>${esc(item.label)}</dt><dd>${esc(item.value)}</dd>`).join("");
    const crumbs = path.map((node, index) =>
      `<button type="button" data-projection-crumb="${index}">${esc(node.label)}</button>`).join('<span aria-hidden="true"> / </span>');
    const rows = entries.map((node) => {
      const children = node.children || [];
      const kind = node.kind === "module_target" ? "module"
        : node.kind === "observed_only_module_target" ? "module without target"
          : node.kind.replaceAll("_", " ");
      return `<button type="button" data-projection-id="${esc(node.id)}"
        aria-pressed="${projectionSelection === node.id}">
        <span><code>${esc(node.label)}</code></span>
        <small>${esc(kind)}${children.length ? ` · ${children.length} entries` : ""}</small></button>`;
    }).join("");
    const selected = entries.find((node) => node.id === projectionSelection);
    const currentDetails = current && details(current)
      ? `<dl class="kv flow-projection-details">${details(current)}</dl>` : "";
    const selectedDetails = selected && details(selected)
      ? `<section aria-label="Selected entry"><h3>${esc(selected.label)}</h3>
        <dl class="kv flow-projection-details">${details(selected)}</dl></section>` : "";
    const context = projectionContext
      ? `<p class="flow-projection-context">${esc(projectionContext.startsWith("No matching scope")
        ? projectionContext : `Context: ${projectionContext}`)}</p>` : "";
    inspectorContent.innerHTML = selectedDetails || currentDetails || context
      || "<p>Select an entry to inspect its recorded details.</p>";
    alternative.innerHTML = `<div class="flow-projection">
      <nav class="flow-projection-breadcrumb" aria-label="${esc(viewMode)} path">
        <button type="button" data-projection-root>${esc(({ actual: "Actual", target: "Target", diff: "Diff" })[viewMode])}</button>
        ${crumbs ? `<span aria-hidden="true"> / </span>${crumbs}` : ""}
      </nav>
      <h2>${esc(title)}</h2>
      ${context}
      ${currentDetails}
      ${rows ? `<div class="flow-item-list">${rows}</div>` : "<p>No entries at this level.</p>"}</div>`;
  }

  function renderAlternative() {
    const focused = captureAlternativeFocus() || pendingAlternativeFocus;
    pendingAlternativeFocus = null;
    const view = level();
    if (["actual", "target", "diff"].includes(viewMode)) {
      renderExplorer();
      restoreAlternativeFocus(focused);
      return;
    }
    if (viewMode === "structure") renderStructure(view);
    else renderReview(view);
    renderInspector(view.edges);
    restoreAlternativeFocus(focused);
  }

  function statBlock() {
    const scope = fullLevel();
    const view = level();
    const edges = viewMode === "diagram" ? visibleEdges() : view.edges;
    const importSites = (items) => items.reduce(
      (total, edge) => total + (edge.kind === "symbol_use" ? 0 : weight(edge)), 0,
    );
    if (opened && opened.module) {
      const inside = (DATA.modules || {})[opened.module] || {};
      const methods = (items) => items.reduce((total, card) => total + (card.members || []).length, 0);
      return `<dl class="kv"><dt>Symbols shown / in module</dt><dd>${view.components.length}/${scope.components.length}</dd><dt>Methods shown / in module</dt><dd>${methods(view.components)}/${methods(scope.components)}</dd><dt>Symbol-use edges shown / in module</dt><dd>${edges.length}/${scope.edges.length}</dd><dt>Used from outside</dt><dd>${(inside.exports || []).length}</dd><dt>Reaches outward</dt><dd>${(inside.imports || []).length}</dd></dl>`;
    }
    if (opened) {
      const owner = componentByLabel.get(opened.component);
      const modules = (items) => items.reduce((total, item) => total + item.modules.length, 0);
      return `<dl class="kv"><dt>Modules shown / in this scope</dt><dd>${modules(view.components)}/${modules(scope.components)}</dd><dt>Groups shown / at this level</dt><dd>${view.components.length}/${scope.components.length}</dd><dt>Connections shown / at this level</dt><dd>${edges.length}/${scope.edges.length}</dd><dt>Import sites shown / at this level</dt><dd>${importSites(edges)}/${importSites(scope.edges)}</dd></dl>`;
    }
    const modules = (items) => items.reduce((total, card) => total + card.modules.length, 0);
    const libraries = scope.components.filter((card) => card.library).length;
    const navigation = scope.components.filter((card) => card.navigation_only).length;
    const violations = new Set(scope.edges.flatMap((edge) => edge.rule_ids)).size;
    return `<dl class="kv"><dt>Declared components</dt><dd>${scope.components.length - libraries - navigation}</dd><dt>Observed libraries</dt><dd>${libraries}</dd><dt>Unassigned module groups</dt><dd>${navigation}</dd><dt>Modules shown / in scope</dt><dd>${modules(view.components)}/${modules(scope.components)}</dd><dt>Edges shown / in scope</dt><dd>${edges.length}/${scope.edges.length}</dd><dt>Import sites shown / in scope</dt><dd>${importSites(edges)}/${importSites(scope.edges)}</dd><dt>Broken edge rules in scope</dt><dd>${violations}</dd></dl>`;
  }

  function topHeaviestEdges(limit) {
    const edges = violationsOnly.checked ? visibleEdges() : level().edges;
    return [...edges]
      .sort(
        (a, b) => weight(b) - weight(a) || a.source.localeCompare(b.source) || a.target.localeCompare(b.target),
      )
      .slice(0, limit);
  }

  function relativeEdgeLabel(edge) {
    const source = edge.source.split(".");
    const target = edge.target.split(".");
    let shared = 0;
    while (shared < source.length - 1 && shared < target.length - 1 &&
      source[shared] === target[shared]) shared += 1;
    return `${source.slice(shared).join(".")} → ${target.slice(shared).join(".")}`;
  }

  function edgeCountLabel(edge) {
    if (edge.kind === "symbol_use") return "symbol-use edge";
    return `${edge.import_sites} import site${edge.import_sites === 1 ? "" : "s"}`;
  }

  function heaviestBlock() {
    const top = topHeaviestEdges(5);
    if (!top.length) return emptyViolationBlock();
    const max = weight(top[0]) || 1;
    const rows = top
      .map(
        (e) =>
          `<div class="row" data-key="${esc(edgeKey(e))}" data-state="${esc(e.state)}" tabindex="0" role="button" aria-label="Select ${esc(e.source)} to ${esc(e.target)}: ${esc(edgeCountLabel(e))}, ${esc(e.state)}" title="${esc(e.source)} → ${esc(e.target)}${e.sites?.length ? ` · ${esc(e.sites.join(", "))}` : ""}"><span class="name"><span class="edge-state">${esc(e.state)}</span> ${esc(relativeEdgeLabel(e))}</span><em>${e.kind === "symbol_use" ? "•" : weight(e)}</em><span class="track"><b style="width:${(100 * weight(e)) / max}%"></b></span></div>`,
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
    if (viewMode === "structure") {
      return `<div class="kicker">Structure</div><h2>${esc(opened?.module || opened?.component || "Repository")}</h2>
        <p>Open a component, package, or module. Tile area counts observed modules or symbol definitions;
        it does not rate their quality.</p>${statBlock()}`;
    }
    if (viewMode === "review") {
      return `<div class="kicker">Review</div><h2>${esc(opened?.module || opened?.component || "Repository")}</h2>
        <p>Select a connection for its rule and import evidence. Open an entry to inspect a smaller scope.
        Missing observations are not a pass.</p>${statBlock()}`;
    }
    if (opened && opened.module) {
      const inside = (DATA.modules || {})[opened.module] || {};
      const reaches = (inside.imports || []).slice(0, 12).map((name) => `<li><code>${esc(name)}</code></li>`).join("");
      return `<div class="kicker">Inside</div><h2>${esc(opened.module)}</h2><p>The functions and classes it declares and the calls and references between them; methods are listed on the card of the class that owns them. A card marked public is imported by another module (AD-24a). Press Escape or use Back to leave.</p>${statBlock()}${reaches ? `<h3>Reaches outward</h3><ul class="names">${reaches}</ul>` : ""}${emptyViolationBlock()}`;
    }
    if (opened && level().declaredInside) {
      const title = (opened.insidePath || []).at(-1) || opened.inside || opened.component;
      return `<div class="kicker">Declared components</div><h2>${esc(title)}</h2><p>These are declared architecture components at this scope. A green connection is allowed by the checked dependency rule; a red one breaks a rule. Select a card once; use Enter, double-click, or Open selected to open one level.</p>${statBlock()}${heaviestBlock()}`;
    }
    if (opened) {
      const owner = componentByLabel.get(opened.component);
      const card = insideScope()?.card || owner;
      const prefix = (opened.path || []).at(-1);
      const outside = prefix ? (card.inner_edges || []).filter((edge) =>
        (edge.source === prefix || edge.source.startsWith(`${prefix}.`)) !==
        (edge.target === prefix || edge.target.startsWith(`${prefix}.`))) : [];
      const outNote = outside.length ? `<p>${outside.length} connections leave this folder, including ${outside.filter((edge) => edge.state === "violation").length} violations. Use the breadcrumb to inspect those crossings.</p>` : "";
      const ownerNote = owner.navigation_only
        ? "These modules have no unique declared owner. This view is navigation only and has no component verdict. "
        : "";
      return `<div class="kicker">Inside</div><h2>${esc(prefix || insideScope()?.card?.label || opened.inside || opened.component)}</h2><p>${ownerNote}Folders follow physical package names; they are not declared architecture boundaries. Connections crossing visible folders are summed. Open a folder to inspect its contents; a red connection still marks a broken rule.</p>${statBlock()}${outNote}${heaviestBlock()}`;
    }
    return `<div class="kicker">Level 2 · components</div><h2>Component flow</h2><p>Declared components are shown with their observed imports. “Unassigned modules” is navigation only and does not imply a component boundary or verdict. Physical package frames are navigation groupings, not owners. Select a box or connection for evidence; use Enter, double-click, or Open selected to open one level.</p>${statBlock()}${heaviestBlock()}`;
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
    const context = viewMode === "diagram" && projectionContext
      ? `<p class="flow-projection-context">${esc(projectionContext)}</p>` : "";
    inspectorContent.innerHTML = `${overview()}${context}`;
    wireHeaviestRows();
  }

  function routeWarningMarkup(attribute, key) {
    const edge = edgeLayer.querySelector(
      `[${attribute}="${CSS.escape(key)}"][data-route-warning="header-overlap"]`,
    );
    return edge
      ? '<p class="flow-layout-warning">Renderer layout warning: no clear route around a frame header; architectural status is unchanged.</p>'
      : "";
  }

  function renderInspector(visible) {
    if (selected?.type === "frame") {
      const frame = diagramPhysicalFrames(fullLevel()).find((item) => item.id === selected.id);
      if (frame) {
        const record = targetNode(frame.id);
        const provenance = record?.details?.filter((detail) => detail.label === "Declared in") || [];
        inspectorContent.innerHTML = `<div class="kicker">Physical navigation</div>
          <h2>${esc(frame.scope)}</h2><p>Physical package · navigation grouping</p>
          <dl class="kv"><dt>Frame identity</dt><dd><code>${esc(frame.id)}</code></dd>
          ${provenance.map((item) => `<dt>Provenance</dt><dd>${esc(item.value)}</dd>`).join("")}</dl>
          <p>This frame groups observed modules by namespace. It is not a semantic component or owner.</p>`;
        return;
      }
    }
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
      const edges = fullLevel().edges;
      const uses = edges.filter((e) => e.source === component.label);
      const usedBy = edges.filter((e) => e.target === component.label);
      const relations = `<dt>Uses</dt><dd>${uses.map((e) => esc(e.target)).join(", ") || "—"}</dd>
        <dt>Used by</dt><dd>${usedBy.map((e) => esc(e.source)).join(", ") || "—"}</dd>`;
      if (component.library) {
        const rules = scopeRules(component);
        inspectorContent.innerHTML = `<div class="kicker">External library</div><h2>${esc(component.display)}</h2>
          <dl class="kv"><dt>Observed import sites</dt><dd>${component.import_sites}</dd>
          <dt>Scope rules</dt><dd>${rules.length}</dd>${relations}</dl>${scopeRuleList(component)}`;
        return;
      }
      if (opened && opened.module) {
        inspectorContent.innerHTML = `<div class="kicker">Symbol</div><h2>${esc(component.label)}</h2>
          <dl class="kv"><dt>Kind</dt><dd>${esc(component.kind || "symbol")}</dd>
          <dt>Outside</dt><dd>${component.public === null ? "not imported elsewhere" : "imported by another module"}</dd>
          ${relations}</dl>
          ${(component.members || []).length ? `<h3>Methods</h3><ul class="plain">${component.members.map((m) => `<li><code>${esc(m)}</code></li>`).join("")}</ul>` : ""}`;
        return;
      }
      if (opened) {
        const scope = insideScope();
        const declaredComponent = Boolean(level().declaredInside && component.declared_inside_component);
        const card = scope?.card || componentByLabel.get(opened.component);
        inspectorContent.innerHTML = `<div class="kicker">${declaredComponent ? "Declared component" : component.folder ? "Physical package" : "Module"}</div><h2>${esc(component.label)}</h2>
          <dl class="kv"><dt>Modules</dt><dd>${component.modules.length}</dd><dt>Import sites touching group</dt><dd>${component.import_sites || 0}</dd>${relations}</dl>
          ${component.folder ? moduleTree({ ...card, modules: component.modules, inner_edges: card.inner_edges }, [...(opened.path || []), component.label]) : `<p>${declaredComponent ? "Use Open selected or Enter to open its declared inside or inspect its physical modules." : component.openable ? "Use Open selected or Enter to inspect its symbols." : "No symbols recorded."}</p>`}`;
        return;
      }
      if (component.navigation_only) {
        inspectorContent.innerHTML = `<div class="kicker">Module inventory · navigation only</div><h2>${esc(component.display || component.label)}</h2>
          <p>These modules have no unique declared owner. This view does not add a component boundary, permission or verdict.</p>
          <dl class="kv"><dt>Modules</dt><dd>${component.modules.length}</dd>${relations}</dl>
          <h3>Physical module tree</h3>${moduleTree(component)}`;
        return;
      }
      const required = component.requires || [];
      const placement = viewMode === "diagram" && !opened
        ? diagramPlacementFor(component) : null;
      const placementDetails = placement ? `<h3>Declared placement annotation</h3><dl class="kv">
        <dt>Status</dt><dd>${esc(placement.status)}</dd>
        <dt>Scopes</dt><dd>${placement.scopes.length
          ? placement.scopes.map((scope) => `<code>${esc(scope)}</code>`).join(", ")
          : placement.status === "unmatched" ? "No unique target component match."
            : "No declared scope available."}</dd>
        ${placement.declaration ? `<dt>Declaration</dt><dd><code>${esc(placement.declaration)}</code></dd>` : ""}
        ${placement.provenance ? `<dt>Declared in</dt><dd>${esc(placement.provenance)}</dd>` : ""}
        <dt>Evidence boundary</dt><dd>This Target annotation does not change Diagram observations, edges, ranks, or verdicts.</dd>
        </dl>` : "";
      inspectorContent.innerHTML = `<div class="kicker">Component</div><h2>${esc(component.label)}</h2>
        <dl class="kv"><dt>Modules</dt><dd>${component.modules.length}</dd>
        ${relations}</dl>
        ${placementDetails}
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
    const display = new Map(level().components.map((card) => [card.label, card.display || card.label]));
    const sourceName = display.get(edge.source) || edge.source;
    const targetName = display.get(edge.target) || edge.target;
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
    inspectorContent.innerHTML = `<div class="kicker">Connection</div><h2>${esc(sourceName)} → ${esc(targetName)}</h2>
      ${sourceName === edge.source && targetName === edge.target ? "" : `<details><summary>Exact names</summary><p><code>${esc(edge.source)}</code> → <code>${esc(edge.target)}</code></p></details>`}
      <dl class="kv"><dt>Verdict</dt><dd>${esc(edge.state)}</dd><dt>${edge.kind === "symbol_use" ? "Relationship" : "Observed import sites"}</dt><dd>${edge.kind === "symbol_use" ? "Symbol use" : edge.import_sites}</dd>${edge.library || !edge.names.length ? "" : `<dt>Interface names</dt><dd>${edge.names.length}</dd>`}</dl>
      ${edge.library ? `<h3>External library scope</h3>${scopeRuleList(edge.scope)}` : ""}
      ${edge.requirement && edge.requirement.component ? `<p>Declared dependency: ${edge.requirement.through && edge.requirement.through.length ? `through <code>${edge.requirement.through.map(esc).join(", ")}</code>` : "interface not narrowed"}${edge.requirement.rationale ? ` — ${esc(edge.requirement.rationale)}` : ""}${edge.requirement.decided_by ? ` (${esc(edge.requirement.decided_by)})` : ""}.</p>` : ""}
      ${edge.kind !== "symbol_use" && (edge.sites || []).length ? `<h3>Example import sites</h3><ul class="plain">${edge.sites.map((site) => `<li><code>${esc(site)}</code></li>`).join("")}</ul>` : ""}
      ${
        edge.rule_ids.length
          ? `<h3>Broken rules</h3><ul class="plain">${edge.rule_ids.map((r) => { const rule = (DATA.rules || {})[r] || {}; return `<li class="violation-card"><code>${esc(r)}</code>${rule.rationale ? ` — ${esc(rule.rationale)}` : ""}${rule.decided_by ? ` (${esc(rule.decided_by)})` : ""}</li>`; }).join("")}</ul>`
          : ""
      }
      ${edge.names.length ? `<details class="flow-names"><summary>Imported names · ${edge.names.length}</summary>${names}</details>` : ""}
      ${routeWarningMarkup("data-key", selected.key)}`;
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
    const padding = 32;
    const nextX = bounds.x - padding;
    const nextY = bounds.y - padding;
    if (!diagramOrigin) diagramOrigin = { x: nextX, y: nextY };
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
    if (scrollX) canvas.scrollLeft += scrollX;
    if (scrollY) canvas.scrollTop += scrollY;
    zoomValue.textContent = `${Math.round(transform.k * 100)}%`;
  }

  function fit() {
    const bounds = viewport.getBBox();
    if (!bounds.width || !bounds.height || !canvas.clientWidth || !canvas.clientHeight) return;
    transform.k = Math.min(
      1.4,
      canvas.clientWidth / (bounds.width + 64),
      canvas.clientHeight / (bounds.height + 64),
    );
    diagramOrigin = null;
    sizeDiagram();
    canvas.scrollLeft = 0;
    canvas.scrollTop = 0;
  }

  function zoomBy(factor) {
    transform.k = Math.min(2.4, Math.max(0.1, transform.k * factor));
    sizeDiagram();
  }

  // render() rebuilds every card, so drag state lives at IIFE scope rather than on a node.
  let dragState = null;
  let framePointer = null;
  let lastFrameTap = null;
  let skipSvgClick = false;
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
  });
  // A press that barely moved is a tap, not a drag. A mouse sits still, a finger never does:
  // three pixels rejected every touch as a drag, which left the lower levels unreachable on a
  // phone. The slack follows the pointer that made the press.
  const TAP_SLACK = { mouse: 3, pen: 6, touch: 12 };
  const endPointer = (event) => {
    if (framePointer) {
      const tapped = framePointer;
      framePointer = null;
      skipSvgClick = true;
      const doubled = lastFrameTap?.id === tapped.id
        && event.timeStamp - lastFrameTap.timeStamp <= 500;
      lastFrameTap = doubled ? null : { id: tapped.id, timeStamp: event.timeStamp };
      if (doubled) enterDiagramFrame(tapped.id);
      else {
        selected = { type: "frame", id: tapped.id };
        selectedSubject = null;
        render();
      }
      return;
    }
    // The kind is read from the press that started the gesture, not from the release: one
    // source for one fact, and pointer capture can hand the release a different shape.
    const slack = dragState ? (TAP_SLACK[dragState.pointerType] ?? TAP_SLACK.touch) : 0;
    const tapped = dragState && dragState.moved <= slack ? dragState.label : null;
    dragState = null;
    const doubled = tapped !== null && lastPointerTap?.label === tapped
      && event.timeStamp - lastPointerTap.timeStamp <= 500;
    lastPointerTap = tapped === null || doubled ? null : { label: tapped, timeStamp: event.timeStamp };
    if (doubled) enter(tapped);
    else if (tapped !== null) selectCard(tapped);
  };
  // A cancelled pointer is the browser taking the gesture away, never a tap: only forget it.
  const cancelPointer = () => {
    dragState = null;
    framePointer = null;
    lastFrameTap = null;
    lastPointerTap = null;
  };
  svg.addEventListener("pointerup", endPointer);
  svg.addEventListener("pointercancel", cancelPointer);
  // Clearing belongs to the background alone. A tap on a card is handled in endPointer, and
  // the browser then sends the click along anyway; since the card no longer carries a click
  // handler to stop it, that click reached this one and wiped the selection the tap had just
  // made. The first tap appeared to work and every following one did nothing.
  svg.addEventListener("click", (event) => {
    if (event.detail > 1 && lastFrameTap) {
      const { id } = lastFrameTap;
      lastFrameTap = null;
      enterDiagramFrame(id);
      return;
    }
    if (skipSvgClick) {
      skipSvgClick = false;
      return;
    }
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
    const insidePath = [opened.inside, ...(opened.insidePath || [])].filter(Boolean);
    if (opened.module) return `Back to ${(opened.path || []).at(-1) || insidePath.at(-1) || opened.component}`;
    if (opened.path && opened.path.length) return `Back to ${opened.path.length > 1 ? opened.path[opened.path.length - 2] : insidePath.at(-1) || opened.component}`;
    if (insidePath.length > 1) return `Back to ${insidePath[insidePath.length - 2]}`;
    if (opened.inside) return `Back to ${opened.component}`;
    return "Back to components";
  }

  function crumbs() {
    const items = [{ label: "Components", state: null }];
    if (!opened) return items;
    items.push({ label: opened.component, state: { component: opened.component, path: [] } });
    if (opened.inside) items.push({ label: opened.inside, state: {
      component: opened.component,
      inside: opened.inside,
      ...(opened.physicalInsideCard && !(opened.insidePath || []).length ? { physicalInsideCard: true } : {}),
      path: [],
    } });
    (opened.insidePath || []).forEach((name, index) => items.push({
      label: name,
      state: {
        component: opened.component,
        inside: opened.inside,
        insidePath: opened.insidePath.slice(0, index + 1),
        ...(opened.physicalInsideCard && index === opened.insidePath.length - 1 ? { physicalInsideCard: true } : {}),
        path: [],
      },
    }));
    (opened.path || []).forEach((name, index) => items.push({ label: name.split(".").pop(), state: { component: opened.component, ...(opened.inside ? { inside: opened.inside } : {}), ...(opened.insidePath ? { insidePath: opened.insidePath } : {}), ...(opened.physicalInsideCard ? { physicalInsideCard: true } : {}), path: opened.path.slice(0, index + 1) } }));
    if (opened.module) items.push({ label: opened.module.split(".").pop(), state: opened });
    return items;
  }

  function updateNavigation() {
    if (viewMode === "target") {
      backButton.hidden = !targetPath.length;
      backButton.textContent = `Back to ${targetPath.length > 1 ? targetNode(targetPath.at(-2))?.label : "Target"}`;
      breadcrumb.hidden = false;
      breadcrumb.textContent = "";
      const entries = [{ label: "Target", depth: 0 }, ...targetPath.map((id, index) => ({
        label: targetNode(id)?.label || id,
        depth: index + 1,
      }))];
      entries.forEach((item, index) => {
        if (index) breadcrumb.append(" / ");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = item.label;
        button.disabled = index === entries.length - 1;
        button.addEventListener("click", () => {
          invalidateOtherViewStates();
          navigationHistory.delete(viewMode);
          projectionContext = null;
          projectionReturnContext = null;
          targetPath = targetPath.slice(0, item.depth);
          targetSelection = null;
          selectedSubject = null;
          positions = {};
          render();
          focusSharedBreadcrumb(item.depth);
        });
        breadcrumb.appendChild(button);
      });
      return;
    }
    if (viewMode === "diagram" && !opened && diagramFramePath.length) {
      const frames = diagramPhysicalFrames(fullLevel());
      const entries = [
        { label: "Diagram", depth: 0 },
        ...diagramFramePath.map((id, index) => {
          const frame = frames.find((item) => item.id === id);
          return {
            label: frame ? `Physical package · navigation grouping: ${frame.scope}` : id,
            depth: index + 1,
            id,
          };
        }),
      ];
      const parent = entries.at(-2);
      backButton.hidden = false;
      backButton.textContent = `Back to ${parent?.label || "Diagram"}`;
      breadcrumb.hidden = false;
      breadcrumb.textContent = "";
      entries.forEach((item, index) => {
        if (index) breadcrumb.append(" / ");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = item.label;
        button.disabled = index === entries.length - 1;
        button.addEventListener("click", () => {
          invalidateOtherViewStates();
          navigationHistory.delete(viewMode);
          projectionContext = null;
          projectionReturnContext = null;
          diagramFramePath = diagramFramePath.slice(0, item.depth);
          selected = item.id ? { type: "frame", id: item.id } : null;
          selectedSubject = null;
          render();
          focusSharedBreadcrumb(item.depth);
        });
        breadcrumb.appendChild(button);
      });
      return;
    }
    if (["actual", "diff"].includes(viewMode)) {
      const rootLabel = viewMode === "actual" ? "Actual" : "Diff";
      const flat = projectionNodes(DATA.explorers[viewMode]);
      const entries = [{ label: rootLabel, depth: 0 }, ...projectionPath.map((id, index) => ({
        label: flat.find(({ node }) => node.id === id)?.node.label || id,
        depth: index + 1,
      }))];
      backButton.hidden = !projectionPath.length;
      backButton.textContent = "Back to " + (entries.at(-2)?.label || rootLabel);
      breadcrumb.hidden = false;
      breadcrumb.textContent = "";
      entries.forEach((item, index) => {
        if (index) breadcrumb.append(" / ");
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = item.label;
        button.disabled = index === entries.length - 1;
        button.addEventListener("click", () => {
          invalidateOtherViewStates();
          navigationHistory.delete(viewMode);
          projectionContext = null;
          projectionReturnContext = null;
          projectionPath = projectionPath.slice(0, item.depth);
          projectionSelection = null;
          selectedSubject = null;
          render();
          focusSharedBreadcrumb(item.depth);
        });
        breadcrumb.appendChild(button);
      });
      return;
    }
    backButton.hidden = !opened;
    breadcrumb.hidden = false;
    if (opened) backButton.textContent = backLabel();
    breadcrumb.textContent = "";
    crumbs().forEach((item, index, all) => {
      if (index) breadcrumb.append(" / ");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = item.label;
      button.disabled = index === all.length - 1;
      button.addEventListener("click", () => {
        invalidateOtherViewStates();
        navigationHistory.delete(viewMode);
        projectionContext = null;
        projectionReturnContext = null;
        opened = item.state;
        selected = null;
        positions = {};
        render();
        focusSharedBreadcrumb(index);
      });
      breadcrumb.appendChild(button);
    });
  }

  function focusSharedBreadcrumb(depth) {
    const target = breadcrumb.querySelectorAll("button")[depth];
    if (target && !target.disabled) {
      target.focus({ preventScroll: true });
      return;
    }
    breadcrumb.tabIndex = -1;
    breadcrumb.focus({ preventScroll: true });
  }

  function enter(label) {
    invalidateOtherViewStates();
    const card = level().components.find((item) => item.label === label);
    if (!card) return;
    selected = { type: "node", label };
    selectSubject(card, "diagram");
    if (opened ? !card.openable : card.library) {
      render();
      return;
    }
    rememberNavigationState();
    diagramFramePath = [];
    if (!opened) {
      opened = { component: label, path: [] };
    } else if (opened.module) {
      return;
    } else if (!opened.physicalInsideCard && (opened.inside || componentByLabel.get(opened.component).inside)) {
      const card = level().components.find((c) => c.label === label);
      if (!card) return;
      if (card.inside) {
        opened = opened.inside
          ? { ...opened, insidePath: [...(opened.insidePath || []), label], path: [] }
          : { component: opened.component, inside: label, path: [] };
      } else if (card.folder) {
        opened = { ...opened, path: [...(opened.path || []), label] };
      } else if (card.opensModule) {
        opened = { ...opened, module: card.opensModule };
      } else if (!opened.inside) {
        opened = { component: opened.component, inside: label, physicalInsideCard: true, path: [] };
      } else {
        opened = {
          ...opened,
          insidePath: [...(opened.insidePath || []), label],
          physicalInsideCard: true,
          path: [],
        };
      }
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
    render();
    if (opened) focusCurrentLevel();
  }

  // One step back per press: a module returns to what held it, a sub-component to its
  // component, a component to the overview.
  function leave() {
    if (!opened) return;
    invalidateOtherViewStates();
    if (restoreNavigationState()) return;
    const departed = opened;
    const history = crumbs();
    opened = history[history.length - 2].state;
    selected = null;
    positions = {};
    render();
    if (viewMode !== "diagram") return;
    const parentLabel = (departed.path || []).at(-1) ??
      (departed.insidePath || []).at(-1) ?? departed.inside ?? departed.component;
    const parentCard = departed.module
      ? fullLevel().components.find((card) => card.opensModule === departed.module)
      : fullLevel().components.find((card) => card.label === parentLabel);
    const target = parentCard && nodeLayer.querySelector(
      `[data-label="${CSS.escape(parentCard.label)}"]`,
    );
    (target || canvas).focus();
  }

  backButton.addEventListener("click", () => {
    if (viewMode === "target" && targetPath.length) {
      invalidateOtherViewStates();
      if (restoreNavigationState()) return;
      projectionContext = null;
      projectionReturnContext = null;
      targetPath.pop();
      targetSelection = null;
      selectedSubject = null;
      positions = {};
      render();
      focusCurrentLevel();
    } else if (["actual", "diff"].includes(viewMode) && projectionPath.length) {
      invalidateOtherViewStates();
      if (restoreNavigationState()) return;
      projectionPath.pop();
      projectionSelection = null;
      selectedSubject = null;
      positions = {};
      render();
      focusCurrentLevel();
    } else if (viewMode === "diagram" && diagramFramePath.length && !opened) {
      invalidateOtherViewStates();
      if (restoreNavigationState()) return;
      selected = { type: "frame", id: diagramFramePath.pop() };
      selectedSubject = null;
      render();
      focusCurrentLevel();
    } else {
      leave();
    }
  });
  toolbar.hidden = false;
  root.querySelector(".flow-views").hidden = false;
  viewButtons.forEach((button) => button.addEventListener("click", () => {
    const nextView = button.dataset.flowView;
    if (nextView === viewMode) return;
    saveViewState(viewMode);
    const projectionView = ["diagram", "actual", "target", "diff"].includes(viewMode)
      && ["diagram", "actual", "target", "diff"].includes(nextView);
    const savedContext = projectionReturnContext;
    const returning = savedContext?.view === nextView ? savedContext : null;
    const currentSource = {
      view: viewMode,
      path: viewMode === "target" ? [...targetPath] : [...projectionPath],
      selection: viewMode === "target" ? targetSelection : projectionSelection,
      subject: selectedSubject ? { ...selectedSubject } : null,
    };
    const source = savedContext && projectionContext ? savedContext : currentSource;
    const counterpart = projectionView && !returning
      ? projectionCounterpart(source.view, nextView, savedContext) : null;
    const previous = projectionView
      ? source.view === "diagram"
        ? [source.subject?.id || source.subject?.file || source.subject?.package
          || (opened?.insidePath || []).at(-1) || opened?.inside || opened?.component].filter(Boolean)
        : [...source.path, source.selection]
          .map((id) => projectionNodes(DATA.explorers[source.view] || [])
            .find(({ node }) => node.id === id)?.node.label)
          .filter(Boolean)
      : [];
    projectionReturnContext = projectionView
      ? returning ? null : savedContext || source
      : null;
    projectionContext = returning ? null : projectionView
      ? counterpart?.context || (!counterpart && previous.length
        ? `No matching scope in this view. Context: ${previous.join(" / ")}` : null)
      : null;
    viewMode = nextView;
    projectionPath = nextView === "target" ? [] : returning?.path || counterpart?.path || [];
    projectionSelection = nextView === "target" ? null : returning?.selection || counterpart?.selection || null;
    targetPath = nextView === "target"
      ? returning?.path || counterpart?.targetPath || [] : [];
    targetSelection = nextView === "target"
      ? returning?.selection || counterpart?.targetSelection || null : null;
    if (projectionView && nextView === "diagram" && !returning) {
      opened = counterpart?.diagramOpened || null;
      selected = counterpart?.diagramSelectionLabel
        ? { type: "node", label: counterpart.diagramSelectionLabel }
        : null;
      positions = {};
      diagramFramePath = [...(counterpart?.diagramFramePath || [])];
      selectedSubject = counterpart?.subject || null;
    }
    const restored = projectionView && nextView === "diagram" && !returning
      ? false : restoreViewState(nextView);
    if (!restored) positions = {};
    render();
    if (restored) requestAnimationFrame(() => {
      const state = viewStates.get(nextView);
      const scroll = scrollViewport(nextView);
      scroll.scrollLeft = state.scrollLeft;
      scroll.scrollTop = state.scrollTop;
      sizeDiagram();
    });
  }));
  responsibilitySearch.addEventListener("input", filterResponsibilities);
  responsibilityList.addEventListener("click", (event) => {
    const button = event.target.closest("[data-responsibility-index]");
    if (!button) return;
    const row = responsibilityRows[Number(button.dataset.responsibilityIndex)];
    invalidateOtherViewStates();
    navigationHistory.clear();
    viewMode = "target";
    projectionContext = null;
    projectionReturnContext = null;
    selectSubject(targetNode(row.id), "target");
    targetPath = [...row.ancestors];
    targetSelection = row.id;
    positions = {};
    render();
    canvas.scrollIntoView({ block: "nearest" });
  });
  focusInput.addEventListener("change", () => {
    focusLabel = focusInput.value || null;
    selected = null;
    positions = {};
    render();
  });
  alternative.addEventListener("click", (event) => {
    const projectionButton = event.target.closest("[data-projection-id]");
    if (projectionButton) {
      const id = projectionButton.dataset.projectionId;
      const entries = projectionPath.reduce((items, parent) =>
        (items.find((item) => item.id === parent)?.children || []), DATA.explorers[viewMode]);
      const node = entries.find((item) => item.id === id);
      if (!node) return;
      selectSubject(node);
      projectionSelection = id;
      render();
      return;
    }
    const crumb = event.target.closest("[data-projection-crumb]");
    if (crumb) {
      invalidateOtherViewStates();
      projectionContext = null;
      projectionReturnContext = null;
      projectionPath = projectionPath.slice(0, Number(crumb.dataset.projectionCrumb) + 1);
      projectionSelection = null;
      selectedSubject = null;
      render();
      return;
    }
    if (event.target.closest("[data-projection-root]")) {
      invalidateOtherViewStates();
      projectionContext = null;
      projectionReturnContext = null;
      projectionPath = [];
      projectionSelection = null;
      selectedSubject = null;
      render();
      return;
    }
    const cardButton = event.target.closest("[data-flow-card]");
    if (cardButton) {
      pendingAlternativeFocus = { attribute: "data-flow-card", value: cardButton.dataset.flowCard };
      const card = level().components.find((item) => item.label === cardButton.dataset.flowCard);
      if (!card) return;
      if ((!opened && !card.library) || (opened && card.openable)) enter(card.label);
      else {
        selected = { type: "node", label: card.label };
        render();
      }
      return;
    }
    const edgeButton = event.target.closest("[data-flow-edge]");
    if (edgeButton) {
      selected = { type: "edge", key: edgeButton.dataset.flowEdge };
      alternative.querySelectorAll("[data-flow-edge]").forEach((button) =>
        button.setAttribute("aria-pressed", String(button.dataset.flowEdge === selected.key)));
      renderInspector(level().edges);
    }
  });
  alternative.addEventListener("dblclick", (event) => {
    const button = event.target.closest("[data-projection-id]");
    if (!button) return;
    const id = button.dataset.projectionId;
    const node = projectionNodes(DATA.explorers[viewMode] || [])
      .find(({ node }) => node.id === id)?.node;
    if (!node?.children?.length) return;
    event.preventDefault();
    invalidateOtherViewStates();
    projectionSelection = id;
    selectSubject(node);
    rememberNavigationState();
    projectionPath.push(id);
    projectionSelection = null;
    render();
    focusCurrentLevel();
  });
  alternative.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    const button = event.target.closest("[data-projection-id]");
    if (!button) return;
    const node = projectionNodes(DATA.explorers[viewMode] || [])
      .find(({ node }) => node.id === button.dataset.projectionId)?.node;
    if (!node?.children?.length) return;
    event.preventDefault();
    invalidateOtherViewStates();
    projectionSelection = node.id;
    selectSubject(node);
    rememberNavigationState();
    projectionPath.push(node.id);
    projectionSelection = null;
    render();
    focusCurrentLevel();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      if (root.dataset.expanded) return;
      if (event.target.matches("input, textarea, select, [contenteditable='true']")) return;
      if (targetDetailsOpen) {
        setTargetDetails(false);
      } else if (viewMode === "target" && targetPath.length) {
        invalidateOtherViewStates();
        if (restoreNavigationState()) return;
        projectionContext = null;
        projectionReturnContext = null;
        targetPath.pop();
        targetSelection = null;
        selectedSubject = null;
        positions = {};
        render();
      } else if (["actual", "diff"].includes(viewMode) && projectionPath.length) {
        invalidateOtherViewStates();
        if (restoreNavigationState()) return;
        projectionContext = null;
        projectionReturnContext = null;
        projectionPath.pop();
        projectionSelection = null;
        selectedSubject = null;
        render();
      } else if (viewMode === "diagram" && diagramFramePath.length && !opened) {
        invalidateOtherViewStates();
        if (restoreNavigationState()) return;
        selected = { type: "frame", id: diagramFramePath.pop() };
        selectedSubject = null;
        render();
      } else if (["actual", "target", "diff"].includes(viewMode)
          && (projectionContext || projectionReturnContext)) {
        invalidateOtherViewStates();
        projectionContext = null;
        projectionReturnContext = null;
        selectedSubject = null;
        render();
      } else if (!["actual", "target", "diff"].includes(viewMode)) {
        leave();
      }
    }
  });

  thresholdInput.addEventListener("input", () => {
    positions = {};
    render();
  });
  violationsOnly.addEventListener("change", () => {
    if (violationsOnly.checked && selected && selected.type === "edge") {
      const edge = level().edges.find((item) => edgeKey(item) === selected.key);
      if (edge && edge.state !== "violation") selected = null;
    }
    positions = {};
    render();
  });
  // Arrange recomputes card positions and leaves filters and zoom alone.
  fitButton.addEventListener("click", () => {
    positions = {};
    render();
  });
  overviewButton.addEventListener("click", fit);
  zoomOutButton.addEventListener("click", () => zoomBy(1 / 1.2));
  zoom100Button.addEventListener("click", () => {
    transform.k = 1;
    sizeDiagram();
  });
  zoomInButton.addEventListener("click", () => zoomBy(1.2));
  resetFiltersButton.addEventListener("click", () => {
    focusLabel = null;
    thresholdInput.value = "0";
    violationsOnly.checked = false;
    positions = {};
    render();
  });
  violationFocus.hidden = false;

  renderLegend();
  renderResponsibilities();
  render();
  window.addEventListener("resize", sizeDiagram);
})();
