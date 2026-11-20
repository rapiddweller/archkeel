"use strict";
// ArchQ Explorer presents recorded evidence; it never computes verdicts.
(function () {
  const F = window.ArchkeelFlow;
  // E5 (issue 1451): every payload has an atlas; flow.js refuses a page without one.
  if (!F || !F.root.hasAttribute("data-atlas")) return;
  const query = () => new URLSearchParams(location.search);

  const A = F.atlas;
  const root = F.root;
  const html = document.documentElement;
  const SVGNS = "http://www.w3.org/2000/svg";
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
  const MOD = isMac ? "⌘" : "Ctrl";
  html.classList.add("ak-canvas");

  // ---------- small DOM helpers ----------
  function h(tag, attrs = {}, ...kids) {
    const element = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs)) {
      if (value === false || value === null || value === undefined) continue;
      if (key === "class") element.className = value;
      else if (key === "style") element.style.cssText = value;
      else if (key.startsWith("on")) element.addEventListener(key.slice(2), value);
      else element.setAttribute(key, value === true ? "" : value);
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) element.append(kid);
    return element;
  }
  function s(tag, attrs = {}) {
    const element = document.createElementNS(SVGNS, tag);
    for (const [key, value] of Object.entries(attrs)) element.setAttribute(key, value);
    return element;
  }
  const ICONS = {
    search: "M11 4a7 7 0 1 1 0 14 7 7 0 0 1 0-14zm9 16-4.3-4.3",
    share: "M12 15V3m0 0L8 7m4-4 4 4M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6",
    moon: "M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z",
    list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
    fit: "M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5",
    focus: "M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8zM12 2v3M12 19v3M2 12h3M19 12h3",
    chevron: "M7 10l5 5 5-5",
    open: "M7 17 17 7M9 7h8v8",
    details: "M4 5h16v14H4zM14 5v14",
  };
  function icon(name) {
    const element = s("svg", { class: "ak-icon", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
      "stroke-width": "1.8", "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" });
    element.append(s("path", { d: ICONS[name] }));
    return element;
  }
  function toast(text) {
    const element = h("div", { class: "ak-toast", role: "status" }, text);
    root.append(element);
    setTimeout(() => element.remove(), 1800);
  }

  // ---------- Atlas indexes (facts come from the payload, never from labels) ----------
  const components = A.components;
  const componentById = new Map(components.map((item) => [item.id, item]));
  const depthOf = (item) => { let depth = 0; for (let p = item.parent_id; p; p = componentById.get(p)?.parent_id) depth += 1; return depth; };
  const pathOf = (item) => { const names = []; for (let c = item; c; c = componentById.get(c.parent_id)) names.unshift(c.label); return names.join(" / "); };

  // ---------- navigation through the report's own routing ----------
  const showComponent = (item) => F.selectComponent(item.id);
  const enterScope = (id) => F.openComponent(id);
  // Issue 1471: a module opens at its level on this page; no run writes a page for each module.
  const showModule = (item) => F.openModule(item.id);
  const showRule = (rule) => F.openRule(rule);

  // ---------- search (pure index + deterministic ranking) ----------
  const KIND = {
    component: { order: 0, letter: "C", color: "var(--accent)", group: "Components" },
    module: { order: 1, letter: "M", color: "var(--ink-muted)", group: "Modules" },
    rule: { order: 2, letter: "R", color: "var(--line-strong)", group: "Rules" },
  };
  const indexes = new Map();
  function search(text) {
    const view = F.state().viewMode;
    if (!indexes.has(view)) indexes.set(view, F.reportScene.searchIndex(view));
    return window.ArchkeelReportScene.search(indexes.get(view), text,
      (F.state().scene?.nodes || []).map((node) => node.id));
  }
  function openResult(row) {
    if (row.kind === "component") showComponent(componentById.get(row.id));
    else if (row.kind === "module") showModule(row.module);
    else showRule(row.rule);
  }

  // ---------- overlays ----------
  let overlay = null;
  function closeOverlay() { overlay?.close(); overlay?.remove(); overlay = null; present({ overlay: null }); }
  function modal(content, className = "ak-palette ak-modal", name = "dialog") {
    closeOverlay();
    const box = h("dialog", { class: className, "aria-label": className === "ak-palette" ? "Search" : "Explorer dialog",
      oncancel: (event) => { event.preventDefault(); closeOverlay(); } },
      h("button", { class: "ak-close", "aria-label": "Close dialog", onclick: closeOverlay }, "×"), content);
    overlay = box;
    present({ overlay: name });
    root.append(overlay);
    box.showModal();
    box.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const focusable = [...box.querySelectorAll("button, input, textarea, a[href]")].filter((item) => !item.disabled);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    });
    return box;
  }

  function openPalette() {
    closePop();
    const input = h("input", { type: "text", placeholder: "Search components, modules and rules", "aria-label": "Search",
      role: "combobox", "aria-expanded": "true", "aria-controls": "ak-results", autocomplete: "off" });
    const list = h("ul", { class: "ak-results", id: "ak-results", role: "listbox" });
    const footer = h("footer", {}, h("span", {}, h("kbd", {}, "↑"), " ", h("kbd", {}, "↓"), " move"),
      h("span", {}, h("kbd", {}, "Enter"), " open"), h("span", {}, h("kbd", {}, "Esc"), " close"));
    const box = modal([input, list, footer], "ak-palette", "search");
    let rows = [], active = 0;
    function draw() {
      rows = search(input.value);
      active = Math.min(active, Math.max(0, rows.length - 1));
      list.replaceChildren();
      if (!rows.length) {
        input.removeAttribute("aria-activedescendant");
        list.append(h("li", { class: "ak-empty", role: "presentation" }, "No matching component, module or rule."));
        return;
      }
      if (!input.value.trim()) list.append(h("li", { class: "ak-group", role: "presentation" }, "On this diagram"));
      let group = null;
      rows.forEach((row, position) => {
        if (input.value.trim() && KIND[row.kind].group !== group) {
          group = KIND[row.kind].group;
          list.append(h("li", { class: "ak-group", role: "presentation" }, group));
        }
        const item = h("li", { class: "ak-result", role: "option", id: `ak-opt-${position}`, "aria-selected": String(position === active),
          onpointermove: () => { if (active !== position) { active = position; mark(); } },
          onclick: () => { closeOverlay(); openResult(row); } },
          h("span", { class: "ak-kind", style: `--k:${KIND[row.kind].color}` }, KIND[row.kind].letter),
          h("span", {}, h("div", { class: "ak-name" }, row.label), h("div", { class: "ak-sub" }, row.sub)),
          row.status ? h("span", { class: "ak-status", "data-s": row.status }, row.status) : h("span"));
        list.append(item);
      });
      mark();
    }
    function mark() {
      list.querySelectorAll(".ak-result").forEach((item, position) => item.setAttribute("aria-selected", String(position === active)));
      const current = list.querySelector(`#ak-opt-${active}`);
      input.setAttribute("aria-activedescendant", current ? current.id : "");
      current?.scrollIntoView({ block: "nearest" });
    }
    input.addEventListener("input", () => { active = 0; draw(); });
    input.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown") { event.preventDefault(); active = Math.min(rows.length - 1, active + 1); mark(); }
      else if (event.key === "ArrowUp") { event.preventDefault(); active = Math.max(0, active - 1); mark(); }
      else if (event.key === "Enter" && rows[active]) { event.preventDefault(); const row = rows[active]; closeOverlay(); openResult(row); }
      else if (event.key === "Escape") { event.preventDefault(); closeOverlay(); }
    });
    draw();
    input.focus();
    return box;
  }

  // ---------- popovers ----------
  let pop = null, popAnchor = null;
  function closePop() {
    if (pop?.contains(document.activeElement)) popAnchor?.focus();
    if (pop?.contains(legendContent)) legendPanel.append(legendContent);
    pop?.remove(); pop = null; popAnchor = null;
    present({ pop: null });
  }
  function openPop(anchor, content, align = "left", name = "menu") {
    closePop();
    popAnchor = anchor;
    present({ pop: name });
    pop = h("div", { class: "ak-pop", role: "menu", "aria-label": anchor.getAttribute("aria-label") || anchor.textContent,
      onkeydown: (event) => {
        const items = [...pop.querySelectorAll("button")];
        const index = items.indexOf(document.activeElement);
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
            : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
        }
      } }, content);
    root.append(pop);
    const box = anchor.getBoundingClientRect();
    const bounds = root.getBoundingClientRect();
    const top = box.bottom + 8 + pop.offsetHeight > Math.min(innerHeight, bounds.bottom)
      ? box.top - pop.offsetHeight - 8 : box.bottom + 8;
    pop.style.top = `${Math.max(8, top - bounds.top)}px`;
    pop.style.left = `${Math.max(8, Math.min(root.clientWidth - pop.offsetWidth - 8,
      (align === "right" ? box.right - pop.offsetWidth : box.left) - bounds.left))}px`;
    pop.querySelector("button")?.focus();
  }
  document.addEventListener("pointerdown", (event) => {
    if (pop && !pop.contains(event.target) && !event.target.closest("[data-ak-pop]")) closePop();
  });

  // ---------- "Belongs to" navigation (up, across, inside) ----------
  function belongsMenu(anchor) {
    const scope = F.state().scope;
    const current = scope ? componentById.get(scope) : null;
    const ancestors = [];
    for (let c = current; c; c = componentById.get(c.parent_id)) ancestors.unshift(c);
    const siblings = current ? components.filter((c) => (c.parent_id ?? null) === (current.parent_id ?? null)) : [];
    const inside = components.filter((c) => (c.parent_id ?? null) === (scope ?? null));
    const childCount = (id) => components.filter((c) => c.parent_id === id).length;
    const item = (label, note, onclick, currentItem = false) =>
      h("button", { role: "menuitem", class: currentItem ? "ak-current" : "", "aria-label": note ? `${label}, ${note}` : null, onclick: () => { closePop(); onclick(); } }, label, note ? h("small", {}, note) : null);
    openPop(anchor, [
      h("h4", {}, "Belongs to"),
      item(A.repository, "system", () => enterScope(null), !current),
      ...ancestors.map((c) => item(`${"  ".repeat(depthOf(c) + 1)}${c.label}`, c.layer || "", () => enterScope(c.id), c.id === scope)),
      siblings.length > 1 ? h("h4", {}, "Same level") : null,
      ...(siblings.length > 1 ? siblings.map((c) => item(c.label, childCount(c.id) ? `${childCount(c.id)} inside` : "modules", () => enterScope(c.id), c.id === scope)) : []),
      inside.length ? h("h4", {}, "Inside") : null,
      ...inside.map((c) => item(c.label, childCount(c.id) ? `${childCount(c.id)} inside` : "modules", () => enterScope(c.id))),
    ], "left", "belongs");
  }

  // ---------- the view state of the presentation choices ----------
  const { decider: DECIDER, perspectives: PERSPECTIVES } = window.ArchkeelReportScene;
  // AD-734: the presentation choices live in the one view state S of flow.js; a change is a dispatch,
  // and flow.js writes the URL. AD-606: the report opens with the language of each component on its
  // box ("language" is the default of S.perspective); "none" is a choice.
  const S = F.S;
  const present = (changes) => F.dispatch({ type: "present", ...changes });

  // ---------- objects drawer ----------
  let drawer = null, drawerShown = null;
  function closeDrawer() {
    const restoreFocus = drawer?.contains(document.activeElement);
    const trigger = drawerShown && rail.querySelector(`[data-drawer="${drawerShown}"]`);
    drawer?.remove(); drawer = null; drawerShown = null;
    if (S.drawer) present({ drawer: null });
    F.syncExpansionInert();
    rail.querySelectorAll("button").forEach((button) => button.setAttribute("aria-expanded", "false"));
    if (restoreFocus) trigger?.focus();
  }
  function toggleDrawer(name, build) {
    const same = drawerShown === name;
    closeDrawer();
    if (same) return;
    drawerShown = name;
    present({ drawer: name });
    drawer = h("aside", { class: "ak-drawer", "aria-label": name }, build());
    root.append(drawer);
    F.syncExpansionInert();
    rail.querySelector(`[data-drawer="${name}"]`)?.setAttribute("aria-expanded", "true");
  }
  // The drawer that S names is the drawer on the page: at the start, and after Back.
  function showDrawer(name) {
    if (drawerShown === name) return;
    if (name === "objects") toggleDrawer(name, objectsDrawer);
    else closeDrawer();
  }
  let sort = { key: "path", dir: 1 };
  function objectsDrawer() {
    const filter = h("input", { type: "search", placeholder: "Filter components", "aria-label": "Filter components" });
    const table = h("table", { class: "ak-table" });
    const columns = [
      ["path", "Component", (c) => pathOf(c)],
      ["layer", "Layer", (c) => c.layer || ""],
      ["status", "Evidence", (c) => c.status],
      ["decided", "Decided by", (c) => DECIDER(c.decided_by)],
      ["modules", "Modules", (c) => c.observed_modules ?? -1],
    ];
    function draw() {
      const needle = filter.value.trim().toLowerCase();
      const onCanvas = new Set((F.state().scene?.nodes || []).map((node) => node.id));
      const getter = columns.find(([key]) => key === sort.key)[2];
      const rows = components.filter((c) => !needle || `${pathOf(c)} ${c.layer || ""} ${c.status} ${c.decided_by}`.toLowerCase().includes(needle))
        .sort((a, b) => { const x = getter(a), y = getter(b); return (x > y ? 1 : x < y ? -1 : 0) * sort.dir; });
      table.replaceChildren(
        h("thead", {}, h("tr", {}, columns.map(([key, label]) => h("th", { scope: "col",
          "aria-sort": sort.key === key ? (sort.dir > 0 ? "ascending" : "descending") : "none" },
          h("button", { onclick: () => {
            sort = { key, dir: sort.key === key ? -sort.dir : 1 }; draw();
            table.querySelector(`[data-sort="${key}"]`)?.focus();
          }, "data-sort": key }, label, sort.key === key ? (sort.dir > 0 ? " ↑" : " ↓") : ""))))),
        h("tbody", {}, rows.map((c) => h("tr", { class: onCanvas.has(c.id) ? "ak-here" : "", tabindex: "0",
          onclick: () => showComponent(c), onkeydown: (event) => { if (event.key === "Enter") showComponent(c); } },
          h("td", { title: c.path || "" }, h("span", { style: `padding-left:${depthOf(c) * 12}px` }, c.label)),
          h("td", {}, c.layer || "—"),
          h("td", {}, h("span", { class: "ak-status", "data-s": c.status }, c.status)),
          h("td", {}, h("span", { class: "ak-dot", style: `--c:${colorOf("decision", DECIDER(c.decided_by))}` }), DECIDER(c.decided_by)),
          h("td", {}, String(c.observed_modules ?? "—"))))));
    }
    filter.addEventListener("input", draw);
    draw();
    return [h("h2", {}, `Objects · ${components.length} components`), filter, table];
  }

  // ---------- share: link, Mermaid, SVG ----------
  function shareMenu(anchor) {
    const item = (label, run) => h("button", { role: "menuitem", onclick: () => { closePop(); run(); } }, label);
    openPop(anchor, [
      item("Copy link to this view", () => copy(location.href, "Link copied")),
      item("Copy diagram as Mermaid", () => copy(mermaid(), "Mermaid copied")),
      item("Download SVG", downloadSvg),
    ], "right", "share");
  }

  // ---------- keyboard controls ----------
  const view = (name) => root.querySelector(`[data-flow-view="${name}"]`)?.click();
  const SHORTCUTS = [
    { keys: [`${MOD} K`, "/"], label: "Search everything", match: (e) => (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !e.metaKey && !e.ctrlKey), run: openPalette },
    { keys: ["Shift C"], label: "Zoom to selection", match: (e) => e.shiftKey && !e.metaKey && !e.ctrlKey && e.code === "KeyC", run: () => F.fit() },
    { keys: ["Shift 1"], label: "Fit whole diagram", match: (e) => e.shiftKey && e.code === "Digit1", run: () => fitDiagram() },
    { keys: ["1", "2", "3"], label: "As-Is · Target · Diff", match: (e) => !e.shiftKey && !e.metaKey && !e.ctrlKey && ["1", "2", "3"].includes(e.key),
      run: (e) => view({ 1: "diagram", 2: "target", 3: "diff" }[e.key]) },
    { keys: ["Alt ↑"], label: "Up one level", match: (e) => e.altKey && e.key === "ArrowUp", run: () => F.dispatch({ type: "up" }) },
    { keys: ["P"], label: "Next perspective", match: (e) => !e.metaKey && !e.ctrlKey && e.key.toLowerCase() === "p", run: () => cyclePerspective() },
    { keys: ["O"], label: "Objects list", match: (e) => !e.metaKey && !e.ctrlKey && e.key.toLowerCase() === "o", run: () => toggleDrawer("objects", objectsDrawer) },
    { keys: [`${MOD} wheel`, "pinch"], label: "Zoom at pointer" },
    { keys: ["Space drag", "middle drag"], label: "Pan over cards" },
    { keys: ["Hover"], label: "Trace incoming and outgoing dependencies" },
    { keys: ["Esc"], label: "Close search, menu, panel or full window, then clear the selection" },
  ];
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    // E3: one Escape ladder: overlay > popover > drawer > expanded > selection, one step per key.
    if (event.key === "Escape") {
      if (overlay) closeOverlay();
      else if (pop) closePop();
      else if (drawer) closeDrawer();
      else if (S.expanded) F.dispatch({ type: "collapse" });
      else if (S.selection || S.module || S.cell !== null) F.dispatch({ type: "clearSelection" });
      else return;
      event.preventDefault();
      return;
    }
    const up = event.altKey && event.key === "ArrowUp";
    if (overlay || event.repeat || event.altKey && !up || event.isComposing
      || event.target.isContentEditable || event.target.closest?.("input, textarea, select")) return;
    const hit = SHORTCUTS.find((item) => item.match?.(event));
    if (!hit) return;
    event.preventDefault();
    hit.run(event);
  });

  const move = (selector) => root.querySelector(selector);
  const markSrc = document.querySelector('link[rel="icon"]')?.href;
  const belongs = h("button", { class: "ak-icon-only", title: "Belongs to · navigate up, across and inside", "aria-label": "Belongs to", "data-ak-pop": "",
    onclick: (event) => belongsMenu(event.currentTarget) }, icon("chevron"));
  const topLeft = h("div", { class: "ak-bar ak-top-left" },
    markSrc ? h("img", { class: "ak-logo", src: markSrc, alt: "" }) : null,
    h("strong", { class: "ak-brand" }, "ArchQ Explorer"),
    move(".flow-breadcrumb"), belongs, h("span", { class: "ak-sep" }), move(".atlas-content-choice"));
  const topCenter = h("div", { class: "ak-bar ak-top-center" }, move(".flow-views"));
  const openSelected = move(".flow-open-selected");
  openSelected?.replaceChildren(icon("open"), "Open");
  const detailsToggle = move(".flow-details-toggle");
  detailsToggle?.replaceChildren(icon("details"), "Details");
  const topRight = h("div", { class: "ak-bar ak-top-right" },
    h("button", { class: "ak-search-btn", onclick: openPalette, "aria-label": "Search" },
      h("span", { style: "display:inline-flex;gap:8px;align-items:center" }, icon("search"), "Search"), h("kbd", {}, `${MOD} K`)),
    openSelected, detailsToggle,
    h("button", { class: "ak-icon-only", title: "Share", "aria-label": "Share", "data-ak-pop": "", onclick: (event) => shareMenu(event.currentTarget) }, icon("share")),
    document.querySelector(".theme-toggle"), move(".flow-fullscreen"));
  const rail = h("div", { class: "ak-bar ak-rail", role: "toolbar", "aria-label": "Panels" },
    h("button", { "data-drawer": "objects", title: "Objects (O)", "aria-label": "Objects", "aria-expanded": "false",
      onclick: () => toggleDrawer("objects", objectsDrawer) }, icon("list")));
  const legendPanel = move(".flow-legend-panel");
  const legendContent = move(".flow-legend");
  legendPanel?.remove();
  const legendButton = h("button", { "data-ak-pop": "", title: "What the lines mean",
    onclick: (event) => openPop(event.currentTarget, [
      h("h4", {}, "Languages"),
      h("div", { class: "ak-language-legend" }, languageNames.map(languageBadge)),
      h("h4", {}, "Relationships"), legendContent,
      A.language_note ? h("p", { class: "ak-sub" }, A.language_note) : null], "left", "legend") }, "Legend");
  root.append(h("div", { hidden: true }, legendPanel));
  const bottomLeft = h("div", { class: "ak-bar ak-bottom-left" }, legendButton, move(".flow-filters"),
    h("span", { class: "ak-run-status" }, `Result: ${A.result}`));
  const summary = move(".atlas-summary");
  summary?.classList.add("ak-scene-summary");
  const tagBar = h("div", { class: "ak-bar ak-bottom-center", role: "toolbar", "aria-label": "Perspectives" });
  // report-presentation.js owns the perspectives, the tag bar and the export of the diagram.
  const { applyPerspective, renderTagBar, cyclePerspective, colorOf, languageNames, languageBadge, copy, mermaid, downloadSvg } =
    window.ArchkeelReportPresentation.create({ F, A, root, html, SVGNS, PERSPECTIVES, h, s, S, present, tagBar, components, toast, modal });
  const zoom = move(".flow-zoom-controls");
  zoom?.querySelector(".flow-fit-overview")?.replaceChildren(icon("fit"));
  zoom?.querySelector(".flow-fit-overview")?.setAttribute("aria-label", "Fit overview");
  zoom?.querySelector(".flow-fit-overview")?.setAttribute("title", "Fit whole diagram (Shift 1)");
  const bottomRight = h("div", { class: "ak-bar ak-bottom-right" },
    h("button", { class: "ak-icon-only", title: "Zoom to selection (Shift C)", "aria-label": "Zoom to selection", onclick: () => F.fit() }, icon("focus")),
    zoom);
  move(".flow-layout").before(topLeft, topCenter, topRight, rail);
  root.append(bottomLeft, tagBar, bottomRight);
  const scrollHint = h("p", { class: "rp-scroll-hint", role: "status", hidden: true },
    "Scroll or press Shift 1 to fit");
  root.querySelector(".flow-map-column")?.append(scrollHint);
  const showScrollHint = () => { scrollHint.hidden = !root.dataset.overflow; };
  new MutationObserver(showScrollHint).observe(root, { attributes: true, attributeFilter: ["data-overflow"] });
  showScrollHint();

  // ---------- keep the chrome in sync with every rendered scene ----------
  // Open each diagram fitted without magnifying small graphs.
  let fittedKey = null;
  F.setMaxFitScale(1);
  // AD-606: in the report the diagram starts with the whole width; a click on a box opens the
  // panel of its facts, and "Details" opens and closes it.
  // AD-734: the state of the URL decides Details (closed unless the link selects a box or cell).
  // The sheet of a box is set in the small body text of the design system.
  root.querySelector(".flow-inspector")?.classList.add("body-sm");
  const fitDiagram = () => F.fit(true, { whole: true });
  // The rows of a wrapped layout follow the shape of the view: lay the diagram out again when the
  // Explorer goes to the full window and back.
  new MutationObserver(() => requestAnimationFrame(() => {
    fittedKey = null;
    F.dispatch({ type: "relayout" });
  })).observe(root, { attributes: true, attributeFilter: ["data-expanded"] });
  root.addEventListener("archkeel:rendered", (event) => {
    applyPerspective();
    if (drawerShown === "objects") { closeDrawer(); toggleDrawer("objects", objectsDrawer); }
    const { scope, viewMode } = F.state();
    // Target and Diff of a contract that declares no dependency say so, in one line.
    topLeft.querySelector(".rp-empty-note")?.remove();
    const noted = F.reportScene.atlas.declared_note;
    if (noted && (viewMode === "target" || viewMode === "diff")) {
      topLeft.append(h("p", { class: "rp-empty-note", role: "status" }, noted));
    }
    const key = `${viewMode}|${scope}|${query().get("content") || ""}`;
    if (key === fittedKey) return;
    fittedKey = key;
    if (event.detail.whole) return;
    requestAnimationFrame(() => {
      if (key === fittedKey) F.fit(!F.state().scene?.moduleOverview);
    });
  });
  addEventListener("popstate", closePop, { capture: true });
  // After flow.js restored S from the URL of the entry.
  addEventListener("popstate", () => { showDrawer(S.drawer); applyPerspective(); });
  root.addEventListener("archkeel:inspect", () => {
    if (matchMedia("(max-width: 900px)").matches) closeDrawer();
  });
  addEventListener("beforeprint", closeDrawer);
  showDrawer(S.drawer);
  renderTagBar();
  if (F.state().scene) applyPerspective();
})();
