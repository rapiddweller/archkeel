  // The canvas: size, fit, zoom, pan, fullscreen, and the keys and the pointer of the diagram.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  function updateFullscreenState() {
    if (document.fullscreenElement === root) {
      root.dataset.expanded = S.expanded = "native";
      fullscreenButton.textContent = "Back to report";
      fullscreenButton.setAttribute("aria-label", "Back to report");
      expandStatus.hidden = true;
    } else if (root.dataset.expanded === "native") {
      restoreExpansion();
    }
    sizeDiagram();
  }

  function syncExpansionInert() {
    if (root.dataset.expanded !== "fallback") return;
    for (const element of document.querySelectorAll("main > *")) {
      if (!element.contains(root) && !expansionRestore.inert.some(([saved]) => saved === element)) {
        expansionRestore.inert.push([element, element.inert]);
      }
    }
    for (const [element, inert] of expansionRestore.inert) {
      element.inert = root.contains(element) ? inert : true;
    }
  }

  function restoreExpansion() {
    if (document.fullscreenElement === root) {
      document.exitFullscreen?.();
      return;
    }
    if (!root.dataset.expanded) return;
    delete root.dataset.expanded;
    S.expanded = null;
    sizeDiagram();
    root.removeAttribute("aria-modal");
    root.removeAttribute("role");
    document.body.style.overflow = expansionRestore.bodyOverflow;
    window.scrollTo(expansionRestore.scrollX, expansionRestore.scrollY);
    for (const [element, inert] of expansionRestore.inert) element.inert = inert;
    const focus = expansionRestore.focus;
    expansionRestore = null;
    fullscreenButton.textContent = "Fullscreen";
    fullscreenButton.setAttribute("aria-label", "Fullscreen");
    expandStatus.hidden = true;
    if (focus?.isConnected) focus.focus({ preventScroll: true });
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
    const padding = 24;
    const nextX = bounds.x - Math.max(padding,
      (canvas.clientWidth / transform.k - bounds.width) / 2);
    const nextY = bounds.y - padding;
    if (!diagramOrigin) {
      diagramOrigin = { x: nextX, y: nextY };
      scrollRemainderX = 0;
      scrollRemainderY = 0;
    }
    const scrollX = 0;
    const scrollY = 0;
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
    // Round outward so CSS pixel quantization cannot shrink fitted text.
    svg.style.width = `${Math.ceil(viewWidth * transform.k + horizontalBorder)}px`;
    svg.style.height = `${Math.ceil(viewHeight * transform.k + verticalBorder)}px`;
    // Native scroll rounding must not accumulate across pointer moves.
    if (scrollX) {
      const nextScroll = canvas.scrollLeft + scrollX + scrollRemainderX;
      canvas.scrollLeft = nextScroll;
      scrollRemainderX = nextScroll - canvas.scrollLeft;
    }
    if (scrollY) {
      const nextScroll = canvas.scrollTop + scrollY + scrollRemainderY;
      canvas.scrollTop = nextScroll;
      scrollRemainderY = nextScroll - canvas.scrollTop;
    }
    zoomValue.textContent = `${Math.round(transform.k * 100)}%`;
    markOverflow();
  }

  let maxFitScale = 1.4;
  // Below this scale the 12 px card text is too small to read (issue 1490): a fit stops here and
  // the canvas scrolls. Only an explicit "fit whole diagram" goes below it.
  const READABLE_SCALE = 0.85;
  let pendingLayoutFitWhole = false;
  function fit(overview = false, { whole = false } = {}) {
    if (layoutPending) {
      pendingLayoutFit = true;
      pendingLayoutFitOverview ||= overview;
      pendingLayoutFitWhole ||= whole;
      return;
    }
    const bounds = viewport.getBBox();
    if (!bounds.width || !bounds.height || !canvas.clientWidth || !canvas.clientHeight) return;
    // Member compartments need readable text; oversized content stays pannable.
    const minimumScale = overview ? whole ? 0 : READABLE_SCALE : 1;
    const widthScale = canvas.clientWidth / (bounds.width + 48);
    transform.k = renderedScene?.moduleOverview && !overview
      ? Math.max(READABLE_SCALE, Math.min(maxFitScale, widthScale, canvas.clientHeight / (bounds.height + 48)))
      : Math.max(minimumScale, Math.min(maxFitScale, widthScale, canvas.clientHeight / (bounds.height + 48)));
    panOffset = { x: 0, y: 0 };
    viewport.removeAttribute("transform");
    diagramOrigin = null;
    sizeDiagram();
    canvas.scrollLeft = 0;
    canvas.scrollTop = 0;
    if (!whole && (renderedScene?.componentOverview || renderedScene?.moduleOverview)
        && (canvas.scrollWidth > canvas.clientWidth + 1 || canvas.scrollHeight > canvas.clientHeight + 1)) {
      // Issue 1618: a diagram larger than the view at the readable zoom opens at its top-left box;
      // the faded edges and the hint say that it goes on.
      const first = renderedScene.nodes
        .filter((node) => positions[node.id])
        .sort((a, b) => positions[a.id].x + positions[a.id].y - positions[b.id].x - positions[b.id].y)[0];
      const position = first && positions[first.id];
      if (position) {
        canvas.scrollLeft = Math.max(0, (position.x - diagramOrigin.x - 24) * transform.k);
        canvas.scrollTop = Math.max(0, (position.y - diagramOrigin.y - 24) * transform.k);
      }
    }
    markOverflow();
  }

  // The sides of the canvas with more of the diagram beyond them (issue 1618).
  function markOverflow() {
    const more = [];
    if (canvas.scrollLeft > 1) more.push("left");
    if (canvas.scrollLeft + canvas.clientWidth < canvas.scrollWidth - 1) more.push("right");
    if (canvas.scrollTop > 1) more.push("top");
    if (canvas.scrollTop + canvas.clientHeight < canvas.scrollHeight - 1) more.push("bottom");
    const value = more.join(" ");
    if (root.dataset.overflow !== value) root.dataset.overflow = value;
  }
  canvas.addEventListener("scroll", markOverflow, { passive: true });

  function zoomBy(factor) {
    const minimumScale = renderedScene?.moduleOverview ? 0 : 0.1;
    transform.k = Math.min(2.4, Math.max(minimumScale, transform.k * factor));
    sizeDiagram();
  }

  // The content under the pointer stays under the pointer. Measured on the SVG box, so
  // centering of narrow diagrams and the pan offset are already included.
  function zoomAt(factor, clientX, clientY) {
    const before = svg.getBoundingClientRect();
    const x = (clientX - before.left) / transform.k, y = (clientY - before.top) / transform.k;
    zoomBy(factor);
    const after = svg.getBoundingClientRect();
    const dx = after.left + x * transform.k - clientX, dy = after.top + y * transform.k - clientY;
    const left = canvas.scrollLeft, top = canvas.scrollTop;
    canvas.scrollLeft += dx;
    canvas.scrollTop += dy;
    // Narrow diagrams cannot scroll; the remainder moves the existing pan offset instead.
    const restX = dx - (canvas.scrollLeft - left), restY = dy - (canvas.scrollTop - top);
    if (Math.abs(restX) > 0.5 || Math.abs(restY) > 0.5) {
      panOffset = { x: panOffset.x - restX / transform.k, y: panOffset.y - restY / transform.k };
      viewport.setAttribute("transform", `translate(${panOffset.x} ${panOffset.y})`);
    }
  }
  let spaceHeld = false;
  const editing = (target) => target.closest?.("input, textarea, select, [contenteditable='true']");
  window.addEventListener("keydown", (event) => {
    if (event.code !== "Space" || event.defaultPrevented || editing(event.target)
      || event.target.closest?.("button, a, summary, [role='button']")
      || !canvas.contains(event.target) && !canvas.matches(":hover")) return;
    event.preventDefault();
    spaceHeld = true;
    svg.classList.add("space-pan");
  });
  window.addEventListener("keyup", (event) => {
    if (event.code !== "Space") return;
    spaceHeld = false;
    svg.classList.remove("space-pan");
  });
  window.addEventListener("blur", () => {
    spaceHeld = false;
    svg.classList.remove("space-pan");
  });
  canvas.addEventListener("wheel", (event) => {
    // Plain wheel and two-finger scroll keep panning natively; pinch arrives as a ctrlKey wheel.
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    zoomAt(Math.exp(-event.deltaY * 0.0015), event.clientX, event.clientY);
  }, { passive: false });
  svg.addEventListener("pointerdown", (event) => {
    const panButton = event.button === 0 || event.button === 1;
    if (!event.isPrimary || !panButton || (!spaceHeld && event.button === 0 && event.target.closest(".node, .hit"))) return;
    capturePointer(svg, event);
    panState = { x: event.clientX, y: event.clientY, offset: { ...panOffset } };
    svg.classList.add("panning");
    event.preventDefault();
  });
  svg.addEventListener("pointermove", (event) => {
    if (panState) {
      panOffset = {
        x: panState.offset.x + (event.clientX - panState.x) / transform.k,
        y: panState.offset.y + (event.clientY - panState.y) / transform.k,
      };
      viewport.setAttribute("transform", `translate(${panOffset.x} ${panOffset.y})`);
    }
  });
  svg.addEventListener("pointerup", (event) => {
    if (panState) {
      skipSvgClick = Math.hypot(event.clientX - panState.x, event.clientY - panState.y) > 3;
      panState = null;
      svg.classList.remove("panning");
    }
  });
  svg.addEventListener("pointercancel", () => {
    panState = null;
    svg.classList.remove("panning");
  });
  svg.addEventListener("click", (event) => {
    if (skipSvgClick) { skipSvgClick = false; return; }
    if (!event.target.closest(".node, .hit")) dispatch({ type: "clearSelection" });
  });
  fullscreenButton.addEventListener("click", async () => {
    if (root.dataset.expanded) {
      restoreExpansion();
      return;
    }
    expansionRestore = {
      focus: document.activeElement,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      bodyOverflow: document.body.style.overflow,
      inert: [...document.querySelectorAll("main > *")].filter((element) =>
        !element.contains(root)).map((element) => [element, element.inert]),
    };
    try {
      if (root.requestFullscreen) {
        await root.requestFullscreen();
        return;
      }
    } catch {
      // A browser or embedding policy can deny the direct request.
    }
    document.body.style.overflow = "hidden";
    root.dataset.expanded = S.expanded = "fallback";
    syncExpansionInert();
    sizeDiagram();
    root.setAttribute("aria-modal", "true");
    root.setAttribute("role", "dialog");
    fullscreenButton.textContent = "Back to report";
    fullscreenButton.setAttribute("aria-label", "Back to report");
    expandStatus.textContent = "Expanded in this window";
    expandStatus.hidden = false;
    fullscreenButton.focus({ preventScroll: true });
  });
  document.addEventListener("fullscreenchange", updateFullscreenState);
  root.addEventListener("keydown", (event) => {
    // E3: Escape is one ladder (report-canvas.js): overlay, popover, drawer, expanded, selection.
    if (event.defaultPrevented || event.target.closest("dialog")) return;
    if (event.key === "Tab" && root.dataset.expanded === "fallback") {
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
