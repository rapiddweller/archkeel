  // The URL round trip of the view state (toQuery, fromQuery), the history policy, and the theme that the Explorer follows (AD-734).
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
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
  const VIEWS = ["diagram", "target", "diff"], DRAWERS = ["objects"];
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
      module: S.module, cell: S.cell, details: S.details, drawer: S.drawer, overlay: S.overlay,
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
