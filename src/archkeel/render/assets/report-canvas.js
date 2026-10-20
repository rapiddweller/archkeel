import { flow as F } from "./flow.js";
import { search as searchScene, sceneToMermaid, decider as DECIDER, perspectives as PERSPECTIVES } from "./report-scene.js";
"use strict";
// ArchQ Explorer presents recorded evidence; it never computes verdicts.
(function () {
  if (!F || !F.root.hasAttribute("data-atlas")) return;
  const query = () => new URLSearchParams(location.search);

  const A = F.atlas;
  const root = F.root;
  const html = document.documentElement;
  const SVGNS = "http://www.w3.org/2000/svg";
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
  const MOD = isMac ? "⌘" : "Ctrl";
  html.classList.add("ak-canvas");
  root.classList.toggle("ak-detail", !A);

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
    overview: "M4 5h16M4 12h10M4 19h7",
    list: "M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01",
    keys: "M3 7h18v10H3zM7 11h.01M11 11h.01M15 11h.01M8 14h8",
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
  const components = A?.components || [];
  const componentById = new Map(components.map((item) => [item.id, item]));
  const depthOf = (item) => { let depth = 0; for (let p = item.parent_id; p; p = componentById.get(p)?.parent_id) depth += 1; return depth; };
  const pathOf = (item) => { const names = []; for (let c = item; c; c = componentById.get(c.parent_id)) names.unshift(c.label); return names.join(" / "); };
  const moduleLevel = new Map();
  for (const level of A?.levels || []) {
    const depth = level.parent_id ? depthOf(componentById.get(level.parent_id)) + 1 : 0;
    for (const module of level.modules) {
      const previous = moduleLevel.get(module.id);
      if (!previous || depth > previous.depth) moduleLevel.set(module.id, { level, depth });
    }
  }

  // ---------- navigation through the report's own routing ----------
  const showComponent = (item) => F.selectComponent(item.id);
  const enterScope = (id) => F.openComponent(id);
  const showModule = (item) => {
    const level = moduleLevel.get(item.id)?.level || A.levels.find((level) => level.parent_id === item.component_id) || A.levels[0];
    location.href = F.moduleHref(item, level);
  };
  const showRule = (rule) => F.openRule(rule);
  function setParam(key, value) {
    if (!["file:", "http:", "https:"].includes(location.protocol)) return;
    const next = query();
    if (value) next.set(key, value); else next.delete(key);
    history.replaceState(null, "", `${location.pathname}?${next}${location.hash}`);
  }

  // ---------- search (pure index + deterministic ranking) ----------
  const KIND = {
    component: { order: 0, letter: "C", color: "#2563eb", group: "Components" },
    module: { order: 1, letter: "M", color: "#7c3aed", group: "Modules" },
    rule: { order: 2, letter: "R", color: "#0f766e", group: "Rules" },
    element: { order: 3, letter: "E", color: "#2563eb", group: "On this diagram" },
  };
  const indexes = new Map();
  function search(text) {
    if (!A) {
      const nodes = F.state().scene?.nodes || [];
      return searchScene(nodes.map((node) => ({
        kind: "element", id: node.id, label: node.label, sub: node.kind,
        text: `${node.label} ${node.id} ${node.kind}`.toLowerCase(),
      })), text, nodes.map((node) => node.id));
    }
    const view = F.state().viewMode;
    if (!indexes.has(view)) indexes.set(view, F.reportScene.searchIndex(view));
    return searchScene(indexes.get(view), text,
      (F.state().scene?.nodes || []).map((node) => node.id));
  }
  function openResult(row) {
    if (row.kind === "element") F.selectElement(row.id);
    else if (row.kind === "component") showComponent(componentById.get(row.id));
    else if (row.kind === "module") showModule(row.module);
    else showRule(row.rule);
  }

  // ---------- overlays ----------
  let overlay = null;
  function closeOverlay() { overlay?.close(); overlay?.remove(); overlay = null; }
  function modal(content, className = "ak-palette ak-modal") {
    closeOverlay();
    const box = h("dialog", { class: className, "aria-label": className === "ak-palette" ? "Search" : "Explorer dialog",
      oncancel: (event) => { event.preventDefault(); closeOverlay(); } },
      h("button", { class: "ak-close", "aria-label": "Close dialog", onclick: closeOverlay }, "×"), content);
    overlay = box;
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
    const input = h("input", { type: "text", placeholder: A ? "Search components, modules and rules" : "Search this diagram", "aria-label": "Search",
      role: "combobox", "aria-expanded": "true", "aria-controls": "ak-results", autocomplete: "off" });
    const list = h("ul", { class: "ak-results", id: "ak-results", role: "listbox" });
    const footer = h("footer", {}, h("span", {}, h("kbd", {}, "↑"), " ", h("kbd", {}, "↓"), " move"),
      h("span", {}, h("kbd", {}, "Enter"), " open"), h("span", {}, h("kbd", {}, "Esc"), " close"));
    const box = modal([input, list, footer], "ak-palette");
    let rows = [], active = 0;
    function draw() {
      rows = search(input.value);
      active = Math.min(active, Math.max(0, rows.length - 1));
      list.replaceChildren();
      if (!rows.length) {
        input.removeAttribute("aria-activedescendant");
        list.append(h("li", { class: "ak-empty", role: "presentation" }, A ? "No matching component, module or rule." : "No matching element on this diagram."));
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
  }
  function openPop(anchor, content, align = "left") {
    closePop();
    popAnchor = anchor;
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
      h("button", { role: "menuitem", class: currentItem ? "ak-current" : "", onclick: () => { closePop(); onclick(); } }, label, note ? h("small", {}, note) : null);
    openPop(anchor, [
      h("h4", {}, "Belongs to"),
      item(A.repository, "system", () => enterScope(null), !current),
      ...ancestors.map((c) => item(`${"  ".repeat(depthOf(c) + 1)}${c.label}`, c.layer || "", () => enterScope(c.id), c.id === scope)),
      siblings.length > 1 ? h("h4", {}, "Same level") : null,
      ...(siblings.length > 1 ? siblings.map((c) => item(c.label, childCount(c.id) ? `${childCount(c.id)} inside` : "modules", () => enterScope(c.id), c.id === scope)) : []),
      inside.length ? h("h4", {}, "Inside") : null,
      ...inside.map((c) => item(c.label, childCount(c.id) ? `${childCount(c.id)} inside` : "modules", () => enterScope(c.id))),
    ]);
  }

  // ---------- perspectives from recorded evidence ----------
  const PALETTE = ["#2563eb", "#e8590c", "#0ca678", "#ae3ec9", "#f59f00", "#1098ad", "#e64980", "#5c7cfa"];
  const categorical = {};
  for (const [key, perspective] of Object.entries(PERSPECTIVES)) {
    if (perspective.colors) continue;
    const values = [...new Set(components.map((c) => perspective.value({ component: c })).filter(Boolean))].sort();
    categorical[key] = Object.fromEntries(values.map((value, i) => [value, PALETTE[i % PALETTE.length]]));
  }
  const colorOf = (key, value) => (PERSPECTIVES[key].colors || categorical[key])[value] || "#868e96";
  let perspective = Object.hasOwn(PERSPECTIVES, query().get("perspective")) ? query().get("perspective") : null;
  let pinnedTag = null;

  function sceneNode(id) { return (F.state().scene?.nodes || []).find((node) => node.id === id); }
  function applyPerspective() {
    const active = PERSPECTIVES[perspective];
    root.toggleAttribute("data-ak-perspective", Boolean(active));
    F.nodeLayer.querySelectorAll("[data-uml-id]").forEach((group) => {
      group.querySelector(".ak-tag")?.remove();
      delete group.dataset.akTag;
      group.style.removeProperty("--ak-tag");
      if (!active) return;
      const node = sceneNode(group.dataset.umlId);
      const value = node && active.value(node);
      if (!value) return;
      group.dataset.akTag = value;
      group.style.setProperty("--ak-tag", colorOf(perspective, value));
      const height = Number(group.querySelector(".card")?.getAttribute("height") || 120);
      const width = Math.min(170, 20 + value.length * 6.8);
      const tag = s("g", { class: "ak-tag", transform: `translate(14 ${height - 11})` });
      tag.append(s("rect", { width: String(width), height: "22", rx: "11" }));
      const text = s("text", { x: "10", y: "15" });
      text.textContent = value;
      tag.append(text);
      group.append(tag);
    });
    if (pinnedTag && (!active || !(F.state().scene?.nodes || []).some((node) => active.value(node) === pinnedTag))) pinnedTag = null;
    highlightTag(pinnedTag);
    renderTagBar();
  }
  function highlightTag(value) {
    const lit = new Set();
    F.nodeLayer.querySelectorAll("[data-uml-id]").forEach((group) => {
      const on = value === null || group.dataset.akTag === value;
      group.classList.toggle("ak-dim", !on);
      if (on) lit.add(group.dataset.umlId);
    });
    F.edgeLayer.querySelectorAll("[data-uml-id]").forEach((edge) => {
      edge.classList.toggle("ak-dim", value !== null && !(lit.has(edge.dataset.umlSource) && lit.has(edge.dataset.umlTarget)));
    });
  }
  function renderTagBar() {
    const focusKey = tagBar.contains(document.activeElement) ? document.activeElement.dataset.focusKey : null;
    const active = PERSPECTIVES[perspective];
    const choices = [["", "None"], ...Object.entries(PERSPECTIVES).map(([key, item]) => [key, item.label])];
    const counts = new Map();
    if (active) for (const node of F.state().scene?.nodes || []) {
      const value = active.value(node);
      if (value) counts.set(value, (counts.get(value) || 0) + 1);
    }
    tagBar.replaceChildren(...[
      h("span", { class: "ak-tagbar-label" }, "Perspective"),
      ...choices.map(([key, label]) => h("button", { "data-focus-key": `perspective:${key}`, "aria-pressed": String((perspective || "") === key),
        onclick: () => { perspective = key || null; pinnedTag = null; setParam("perspective", perspective); applyPerspective(); } }, label)),
      active ? h("span", { class: "ak-sep" }) : null,
      ...(active ? [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([value, count]) =>
        h("button", { class: "ak-chip", "data-focus-key": `tag:${value}`, style: `--chip:${colorOf(perspective, value)}`, "aria-pressed": String(pinnedTag === value),
          title: `Highlight ${value}`,
          onpointerenter: () => highlightTag(value), onpointerleave: () => highlightTag(pinnedTag),
          onclick: () => { pinnedTag = pinnedTag === value ? null : value; highlightTag(pinnedTag); renderTagBar(); } },
          h("i"), value, h("b", {}, String(count)))) : []),
      active && !counts.size ? h("span", { class: "ak-tagbar-label" }, "No tagged objects on this diagram") : null,
    ].filter(Boolean));
    if (focusKey) [...tagBar.querySelectorAll("button")].find((button) => button.dataset.focusKey === focusKey)?.focus({ preventScroll: true });
  }
  function cyclePerspective() {
    const keys = [null, ...Object.keys(PERSPECTIVES)];
    perspective = keys[(keys.indexOf(perspective) + 1) % keys.length];
    pinnedTag = null;
    setParam("perspective", perspective);
    applyPerspective();
  }

  // ---------- drawers: overview (health check) and objects list ----------
  let drawer = null, drawerName = null;
  let overviewEvidence = [];
  const explore = root.querySelector(".flow-explore");
  const exploreHome = explore?.parentElement;
  function closeDrawer() {
    const restoreFocus = drawer?.contains(document.activeElement);
    const trigger = drawerName && rail.querySelector(`[data-drawer="${drawerName}"]`);
    if (drawerName === "overview") F.setExploreOpen(false);
    if (drawerName === "overview" && explore && exploreHome) exploreHome.append(explore);
    if (drawerName === "overview") {
      root.prepend(summary);
      document.querySelector(".report-shell").append(...overviewEvidence);
      overviewEvidence = [];
    }
    drawer?.remove(); drawer = null; drawerName = null;
    F.syncExpansionInert();
    rail.querySelectorAll("button").forEach((button) => button.setAttribute("aria-expanded", "false"));
    if (restoreFocus) trigger?.focus();
  }
  function toggleDrawer(name, build) {
    const same = drawerName === name;
    closeDrawer();
    if (same) return;
    drawerName = name;
    drawer = h("aside", { class: "ak-drawer", "aria-label": name }, build());
    root.append(drawer);
    if (name === "overview") F.setExploreOpen(true);
    F.syncExpansionInert();
    rail.querySelector(`[data-drawer="${name}"]`)?.setAttribute("aria-expanded", "true");
  }
  function overviewDrawer() {
    const body = [h("h2", {}, "Health check"),
      h("p", {}, `Whole-run rules: ${A.declared_rules} · Source observation: ${A.observation_complete}`), summary];
    if (explore) { explore.hidden = false; body.push(explore); }
    overviewEvidence = [...document.querySelectorAll(".report-shell > .atlas-structure-overview, .report-shell > .atlas-source")];
    body.push(...overviewEvidence);
    return body;
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
  async function copy(text, done) {
    try { await navigator.clipboard.writeText(text); toast(done); }
    catch { const area = h("textarea", { readonly: true }, text); modal([h("h2", {}, "Copy manually"), area]); area.select(); }
  }
  const mermaid = () => sceneToMermaid(F.state().scene);
  function downloadSvg() {
    const clone = F.svg.cloneNode(true);
    // Computed styles survive without report ancestors, classes or theme variables.
    const originals = [F.svg, ...F.svg.querySelectorAll("*")];
    const copies = [clone, ...clone.querySelectorAll("*")];
    const properties = ["fill", "stroke", "stroke-width", "stroke-dasharray", "stroke-linecap", "stroke-linejoin",
      "opacity", "fill-opacity", "stroke-opacity", "font-family", "font-size", "font-weight", "font-style",
      "text-anchor", "dominant-baseline", "paint-order", "visibility", "display", "rx", "ry"];
    originals.forEach((source, index) => {
      const style = getComputedStyle(source);
      copies[index].removeAttribute("style");
      for (const property of properties) copies[index].style.setProperty(property, style.getPropertyValue(property));
      for (const property of ["marker-start", "marker-mid", "marker-end"]) {
        const marker = style.getPropertyValue(property).match(/#([^"')]+)["']?\)/);
        if (marker) copies[index].style.setProperty(property, `url(#${marker[1]})`);
      }
      copies[index].removeAttribute("tabindex");
    });
    clone.setAttribute("xmlns", SVGNS);
    clone.setAttribute("width", String(F.svg.clientWidth));
    clone.setAttribute("height", String(F.svg.clientHeight));
    clone.style.background = getComputedStyle(html).getPropertyValue("--ak-canvas");
    const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" });
    const link = h("a", { href: URL.createObjectURL(blob), download: `${A?.repository || "architecture"}-${F.state().viewMode}-${F.state().scope || "system"}.svg` });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    toast("SVG download started");
  }
  function shareMenu(anchor) {
    const item = (label, run) => h("button", { role: "menuitem", onclick: () => { closePop(); run(); } }, label);
    // An over-budget diagram is not drawn, so there is no diagram to export.
    const drawn = !F.state().scene?.overBudget;
    openPop(anchor, [
      item("Copy link to this view", () => copy(location.href, "Link copied")),
      ...(drawn ? [item("Copy diagram as Mermaid", () => copy(mermaid(), "Mermaid copied")),
        item("Download SVG", downloadSvg)] : []),
    ], "right");
  }

  // ---------- shortcuts: one table drives handlers and help ----------
  const view = (name) => root.querySelector(`[data-flow-view="${name}"]`)?.click();
  const SHORTCUTS = [
    { keys: [`${MOD} K`, "/"], label: "Search everything", match: (e) => (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !e.metaKey && !e.ctrlKey), run: openPalette },
    { keys: ["Shift C"], label: "Zoom to selection", match: (e) => e.shiftKey && !e.metaKey && !e.ctrlKey && e.code === "KeyC", run: () => F.fit() },
    { keys: ["Shift 1"], label: "Fit whole diagram", match: (e) => e.shiftKey && e.code === "Digit1", run: () => fitDiagram() },
    { keys: ["1", "2", "3"], label: "As-Is · Target · Diff", match: (e) => !e.shiftKey && !e.metaKey && !e.ctrlKey && ["1", "2", "3"].includes(e.key),
      run: (e) => view({ 1: "diagram", 2: "target", 3: "diff" }[e.key]) },
    ...(A ? [
      { keys: ["P"], label: "Next perspective", match: (e) => !e.metaKey && !e.ctrlKey && e.key.toLowerCase() === "p", run: cyclePerspective },
      { keys: ["O"], label: "Objects list", match: (e) => !e.metaKey && !e.ctrlKey && e.key.toLowerCase() === "o", run: () => toggleDrawer("objects", objectsDrawer) },
    ] : []),
    { keys: ["?"], label: "Keyboard shortcuts", match: (e) => e.key === "?", run: () => help() },
    { keys: [`${MOD} wheel`, "pinch"], label: "Zoom at pointer" },
    { keys: ["Space drag", "middle drag"], label: "Pan over cards" },
    { keys: ["Hover"], label: "Trace incoming and outgoing dependencies" },
    { keys: ["Esc"], label: "Close search, menu or panel" },
  ];
  function help() {
    modal([h("h2", {}, "Keyboard shortcuts"), h("table", {}, h("tbody", {}, SHORTCUTS.map((item) =>
      h("tr", {}, h("td", {}, item.keys.flatMap((key, i) => [i ? " or " : null, h("kbd", {}, key)])), h("td", {}, item.label)))))]);
  }
  document.addEventListener("keydown", (event) => {
    if (event.defaultPrevented) return;
    if (event.key === "Escape") { if (overlay) closeOverlay(); else if (pop) closePop(); else if (drawer) closeDrawer(); return; }
    if (overlay || event.repeat || event.altKey || event.isComposing
      || event.target.isContentEditable || event.target.closest?.("input, textarea, select")) return;
    const hit = SHORTCUTS.find((item) => item.match?.(event));
    if (!hit) return;
    event.preventDefault();
    hit.run(event);
  });

  // ---------- assemble the chrome (moves existing controls; their listeners stay intact) ----------
  const move = (selector) => root.querySelector(selector);
  const markSrc = document.querySelector('link[rel="icon"]')?.href;
  const belongs = h("button", { class: "ak-icon-only", title: "Belongs to · navigate up, across and inside", "aria-label": "Belongs to", "data-ak-pop": "",
    onclick: (event) => belongsMenu(event.currentTarget) }, icon("chevron"));
  const topLeft = h("div", { class: "ak-bar ak-top-left" },
    markSrc ? h("img", { class: "ak-logo", src: markSrc, alt: "" }) : null,
    h("strong", { class: "ak-brand" }, "ArchQ Explorer"),
    move(".flow-breadcrumb"), A ? belongs : null, h("span", { class: "ak-sep" }), move(".atlas-content-choice"));
  const topCenter = h("div", { class: "ak-bar ak-top-center" }, move(".flow-views"));
  const openSelected = move(".flow-open-selected");
  openSelected?.replaceChildren(icon("open"), "Open");
  const detailsToggle = move(".flow-details-toggle");
  detailsToggle?.replaceChildren(icon("details"), "Details");
  const back = !A ? move(".flow-back") : null;
  back?.setAttribute("aria-label", back.textContent);
  const topRight = h("div", { class: "ak-bar ak-top-right" },
    h("button", { class: "ak-search-btn", onclick: openPalette, "aria-label": "Search" },
      h("span", { style: "display:inline-flex;gap:8px;align-items:center" }, icon("search"), "Search"), h("kbd", {}, `${MOD} K`)),
    openSelected, detailsToggle,
    h("button", { class: "ak-icon-only", title: "Share", "aria-label": "Share", "data-ak-pop": "", onclick: (event) => shareMenu(event.currentTarget) }, icon("share")),
    document.querySelector(".theme-toggle"), move(".flow-fullscreen"));
  const rail = h("div", { class: "ak-bar ak-rail", role: "toolbar", "aria-label": "Panels" },
    back,
    A ? h("button", { "data-drawer": "overview", title: "Health check", "aria-label": "Health check", "aria-expanded": "false",
      onclick: () => toggleDrawer("overview", overviewDrawer) }, icon("overview")) : null,
    A ? h("button", { "data-drawer": "objects", title: "Objects (O)", "aria-label": "Objects", "aria-expanded": "false",
      onclick: () => toggleDrawer("objects", objectsDrawer) }, icon("list")) : null,
    h("button", { title: "Keyboard shortcuts (?)", "aria-label": "Keyboard shortcuts", onclick: help }, icon("keys")));
  const legendPanel = move(".flow-legend-panel");
  const legendContent = move(".flow-legend");
  legendPanel?.remove();
  const legendButton = h("button", { "data-ak-pop": "", title: "What the lines mean",
    onclick: (event) => openPop(event.currentTarget, [h("h4", {}, "Legend"), legendContent]) }, "Legend");
  root.append(h("div", { hidden: true }, legendPanel));
  const bottomLeft = h("div", { class: "ak-bar ak-bottom-left" }, legendButton, move(".flow-filters"),
    A ? h("span", { class: "ak-run-status" }, `Rules: ${A.declared_rules} · Observation: ${A.observation_complete}`) : null);
  if (!A) {
    bottomLeft.append(h("div", { class: "ak-detail-actions" },
      move(".flow-member-previews"), move(".flow-use-summary"), move(".flow-arrange")));
    bottomLeft.querySelector(".flow-filter-controls").append(move(".flow-unassigned-code"), move(".flow-zoom-100"));
    move(".flow-element-index").classList.add("ak-element-index");
  }
  const summary = move(".atlas-summary");
  if (summary) summary.classList.add("ak-scene-summary");
  const tagBar = h("div", { class: "ak-bar ak-bottom-center", role: "toolbar", "aria-label": "Perspectives" });
  const zoom = move(".flow-zoom-controls");
  zoom?.querySelector(".flow-fit-overview")?.replaceChildren(icon("fit"));
  zoom?.querySelector(".flow-fit-overview")?.setAttribute("aria-label", "Fit overview");
  zoom?.querySelector(".flow-fit-overview")?.setAttribute("title", "Fit whole diagram (Shift 1)");
  const bottomRight = h("div", { class: "ak-bar ak-bottom-right" },
    h("button", { class: "ak-icon-only", title: "Zoom to selection (Shift C)", "aria-label": "Zoom to selection", onclick: () => F.fit() }, icon("focus")),
    zoom);
  root.append(topLeft, topCenter, topRight, rail, bottomLeft, tagBar, bottomRight);

  // ---------- keep the chrome in sync with every rendered scene ----------
  // Open each diagram fitted without magnifying small graphs.
  let fittedKey = null;
  if (A) F.setMaxFitScale(1);
  const fitDiagram = () => F.fit(true);
  root.addEventListener("archkeel:rendered", () => {
    back?.setAttribute("aria-label", back.textContent);
    if (!A) return;
    if (["file:", "http:", "https:"].includes(location.protocol))
      perspective = Object.hasOwn(PERSPECTIVES, query().get("perspective")) ? query().get("perspective") : null;
    applyPerspective();
    if (drawerName === "objects") { const same = drawerName; closeDrawer(); toggleDrawer(same, objectsDrawer); }
    const { scope, viewMode } = F.state();
    const key = `${viewMode}|${scope}|${query().get("content") || ""}`;
    if (key !== fittedKey) {
      fittedKey = key;
      requestAnimationFrame(() => F.fit(!F.state().scene?.moduleOverview));
    }
  });
  addEventListener("popstate", () => {
    closePop();
    perspective = Object.hasOwn(PERSPECTIVES, query().get("perspective")) ? query().get("perspective") : null;
    pinnedTag = null;
  }, { capture: true });
  const revealFindings = () => {
    if (drawerName !== "overview") toggleDrawer("overview", overviewDrawer);
  };
  root.addEventListener("archkeel:findings", revealFindings);
  root.addEventListener("archkeel:inspect", () => {
    if (matchMedia("(max-width: 900px)").matches) closeDrawer();
  });
  addEventListener("beforeprint", closeDrawer);
  if (/^#atlas-(rule|finding)-/.test(location.hash)) revealFindings();
  if (A) {
    renderTagBar();
    if (F.state().scene) applyPerspective();
  } else tagBar.remove();
})();
