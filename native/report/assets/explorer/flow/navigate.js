  // Select and open a box, a module or a level, and the links of the page to them.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  function selectArchitectureSubject(type, id) {
    S.module = S.view !== "target" && REPORT_SCENE.atlasModuleById(id) ? id : null; S.cell = null;
    S.selection = { type, id };
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
    else openAtlasComponent(id, renderedScene?.grouped ? "modules" : null, { whole: true });
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

  function switchArchitectureView(nextView) {
    // E3: the view of the page is not a new view: fullscreen and the key of the current view lay
    // the diagram out again and keep the selection.
    if (nextView === S.view) { relayout(); return; }
    navigate();
    S.view = nextView;
    if (nextView === "target") { S.cell = null; S.module = null; }
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
    S.cell = null;
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

  function openAtlasComponent(id, content = null, { whole = false } = {}) {
    if (!ATLAS.levels.some((level) => level.parent_id === id)) return;
    navigate();
    S.path = REPORT_SCENE.componentRoute(id).map((item) => ({ id: item.id, origin: "observed" }));
    S.content = content;
    S.selection = null;
    setTargetDetails(false);
    S.module = null; S.cell = null;
    positions = Object.create(null); render(); fit(whole, { whole }); focusCurrentLevel();
  }
