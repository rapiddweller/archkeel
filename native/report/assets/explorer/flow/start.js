  // Wire the controls, publish window.ArchkeelFlow, and draw the first level.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
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


  detailsToggle.addEventListener("click", () => dispatch({ type: "setDetails", open: !S.details }));
  if (NAV) {
    setTargetDetails(true);
    readRoute();
    document.querySelector(".theme-toggle").addEventListener("click", () =>
      dispatch({ type: "setTheme", theme: document.documentElement.dataset.theme !== "light" ? "light" : "dark" }));
    window.addEventListener("popstate", () => dispatch({ type: "restoreRoute" }));
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
