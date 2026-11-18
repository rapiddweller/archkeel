  // Finding counts and links used by the Explorer diagram and fact sheet.
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
  function openAtlasFindingHash(requestedId = null) {
    let id = requestedId;
    if (id === null) {
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { pendingAtlasFindingHash = null; return; }
    }
    if (openBoundaryPermissionHash(id)) return;
    if (!id.startsWith("atlas-assessment-")) {
      pendingAtlasFindingHash = null;
      return;
    }
    const target = document.getElementById(id);
    if (!target) { pendingAtlasFindingHash = id; return; }
    pendingAtlasFindingHash = null;
    if (inspector.contains(target)) setTargetDetails(true);
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
