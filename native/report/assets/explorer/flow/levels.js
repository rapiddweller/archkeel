  // Render a level of the atlas: its layout, boxes, edges, crumbs, and the notice of an unknown scope.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
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


  const atlasOwnerPalette = ["var(--line-strong)", "var(--ink-subtle)", "var(--ink-muted)", "var(--line-strong)", "var(--ink-subtle)", "var(--ink-muted)"];
  const atlasComponentIds = ATLAS.components.map((item) => item.id).sort();
  function atlasOwnerColor(componentId) {
    const index = atlasComponentIds.indexOf(componentId);
    return index < 0 ? null : { index, color: atlasOwnerPalette[index % atlasOwnerPalette.length] };
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

  function atlasHasChoice(level, view = S.view) { return Boolean(level.component_ids.length && REPORT_SCENE.atlasModules(level, view).length); }

  function atlasContentPane(level) {
    const modules = REPORT_SCENE.atlasModules(level, S.view), choice = root.querySelector(".atlas-content-choice");
    const content = level.component_ids.length ? S.content === "modules" && modules.length ? "modules" : "components" : "modules";
    root.dataset.content = content;
    choice.hidden = !atlasHasChoice(level);
    const componentLabel = !level.parent_id && level.component_ids.every((id) => id.startsWith("PART:"))
      ? "Parts" : "Components";
    choice.innerHTML = [["components", level.component_ids.length, componentLabel], ["modules", modules.length, "Modules"]].map(([kind, count, label]) =>
      `<button type="button" class="flow-fit" data-content="${kind}" aria-pressed="${content === kind}">${label} (${count})</button>`).join("");
    choice.querySelectorAll("button").forEach((button) => button.onclick = () =>
      dispatch({ type: "setContent", content: button.dataset.content }));
    return content;
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
    const whole = pendingLayoutFitWhole;
    queueMicrotask(() => root.dispatchEvent(new CustomEvent("archkeel:rendered", { detail: { whole } })));
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
