  // The one door of a user action: dispatch(action) and its transitions (AD-734).
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  // The presentation choices of report-canvas.js. dispatch stores them in S; their effects stay there.
  const PRESENTATION = ["perspective", "pinnedTag", "drawer", "overlay", "pop"];

  // E3: up one level is derived from S.path; the level that you leave is selected in its parent.
  function atlasUp() {
    if (!S.path.length) return;
    navigate();
    const child = S.path.at(-1);
    S.path = S.path.slice(0, -1);
    S.selection = { type: "node", id: child.id }; S.module = null; S.cell = null; S.content = null;
    routeNotice = null; positions = Object.create(null); render(); fit();
  }

  // A new layout of the same state: the size of the page changed.
  function relayout() { positions = Object.create(null); render(); fit(); }

  function goToDepth(depth) {
    navigate();
    S.path = S.path.slice(0, depth); S.selection = null; routeNotice = null;
    S.module = null; S.cell = null; S.content = null; positions = Object.create(null); render(); fit();
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
      case "clearSelection": S.selection = null; S.module = null; S.cell = null; render(); break;
      case "selectEdgeCell": selectAtlasSheet(atlasLevel(), { cell: action.cell, module: null, selection: null }); break;
      case "selectEdgeSource":
        selectAtlasSheet(atlasLevel(), { selection: { type: "node", id: action.id }, module: null, cell: null }); break;
      case "setDetails": setTargetDetails(action.open); render(); fit(); break;
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
