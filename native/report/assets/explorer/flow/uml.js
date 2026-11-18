  // Draw the cards, frames and edges of a scene as SVG, and light a focus and its neighbours.
  // A part of the Explorer: tools/browser_runtime.py joins the parts of flow/ into one script.
  function wrapText(value, maxWidth, font) {
    const text = String(value ?? "");
    measureText.font = font;
    const lines = [];
    let line = "";
    for (const word of text.split(/(\s+)|(?<=[_/])|(?<=[a-z])(?=[A-Z])/).filter(Boolean)) {
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

  function cardHeight(id) {
    return cardHeights.get(id) ?? CARD.h;
  }

  function umlSymbol(kind) {
    const icon = el("g", { class: "uml-icon", "aria-hidden": "true",
      transform: `translate(${CARD.w - 29},11)` });
    if (kind === "component" || kind === "library") {
      icon.append(el("rect", { x: "5", y: "1", width: "15", height: "17" }),
        el("rect", { x: "0", y: "5", width: "7", height: "4" }),
        el("rect", { x: "0", y: "12", width: "7", height: "4" }));
    } else if (kind === "package") {
      icon.appendChild(el("path", { d: "M0,2 h8 l3,4 h13 v14 h-24 z" }));
    } else if (["module", "file"].includes(kind)) {
      icon.appendChild(el("path", { d: "M4,0 h11 l6,6 v16 h-17 z M15,0 v6 h6" }));
    } else if (kind === "interface") {
      icon.appendChild(el("circle", { cx: "11", cy: "10", r: "8" }));
    } else if (["class", "mixin", "enum"].includes(kind)) {
      icon.append(el("rect", { x: "1", y: "0", width: "21", height: "23" }),
        el("path", { d: kind === "class" ? "M1,8 h21 M1,15 h21" : "M1,8 h21" }));
    } else if (["method", "function"].includes(kind)) {
      const glyph = el("text", { x: "0", y: "15" });
      glyph.textContent = kind === "method" ? "()" : "ƒ";
      icon.appendChild(glyph);
    }
    return icon.childElementCount ? icon : null;
  }

  function drawUmlCard(node) {
    const position = positions[node.id];
    const group = el("g", {
      class: `node uml-card ${node.kind}`, transform: `translate(${position.x},${position.y})`,
      tabindex: "0", role: "button", "aria-label": node.label,
      "data-uml-id": node.id, "data-uml-kind": node.kind, "data-label": node.label,
    });
    group.appendChild(el("rect", {
      class: "card", width: String(CARD.w), height: String(cardHeight(node.id)),
      rx: ["class", "interface", "enum", "mixin"].includes(node.kind) ? "2" : "8",
    }));
    group.appendChild(el("path", { class: "uml-kind-accent", d: `M16,2 H${CARD.w - 16}` }));
    if (node.violation) group.appendChild(el("rect", {
      class: "tick violated", width: "3", height: String(cardHeight(node.id) - 24), x: "0", y: "12",
    }));
    const kind = el("text", { class: "stereotype", x: "16", y: "19" });
    const stereotype = node.kind === "class" && node.entity?.modifiers.includes("mixin")
      ? "mixin class" : node.kind === "enum" ? "enumeration"
        : node.kind === "enum_literal" ? "enumeration literal" : node.kind;
    kind.textContent = `«${stereotype}»${node.outside ? " · outside" : ""}`;
    group.appendChild(kind);
    const name = createWrappedText(node.label, {
      class: "label", x: "16", y: "37",
      "text-decoration": node.entity?.modifiers.includes("static") ? "underline" : "none",
    },
      CARD.w - 48, `600 14px ${sansFontFamily}`, 18);
    group.appendChild(name);
    const nameLines = wrapText(node.label, CARD.w - 48, `600 14px ${sansFontFamily}`).length;
    group.appendChild(createWrappedText(node.meta, {
      class: "meta", x: "16", y: String(42 + nameLines * 18),
      "text-decoration": node.entity?.modifiers.includes("static") ? "underline" : "none",
    }, CARD.w - 32, `12px ${monoFontFamily}`, 14));
    for (const section of umlCompartments(node)) {
      group.appendChild(el("path", { class: "uml-divider", d: `M0,${section.top} H${CARD.w}` }));
      const heading = el("text", { class: "uml-compartment-title", x: "12", y: String(section.top + 15) });
      heading.textContent = section.label;
      group.appendChild(heading);
      let y = section.top + 32;
      for (const line of section.lines) {
        group.appendChild(createWrappedText(line.text, {
          class: "uml-member", x: "12", y: String(y),
          "text-decoration": line.static ? "underline" : "none",
        }, CARD.w - 24, `11px ${monoFontFamily}`, 14));
        y += wrapText(line.text, CARD.w - 24, `11px ${monoFontFamily}`).length * 14;
      }
    }
    const symbol = umlSymbol(node.kind);
    if (symbol) group.appendChild(symbol);
    const title = el("title");
    title.textContent = node.tooltip;
    group.appendChild(title);
    return group;
  }

  function umlCompartments(node) {
    let top = 46 + wrapText(node.label, CARD.w - 48, `600 14px ${sansFontFamily}`).length * 18
      + wrapText(node.meta, CARD.w - 32, `12px ${monoFontFamily}`).length * 14;
    return (node.sections || []).map((section) => {
      const bottom = top + 30 + section.lines.reduce((height, line) =>
        height + wrapText(line.text, CARD.w - 24, `11px ${monoFontFamily}`).length * 14, 0);
      const compartment = { ...section, top, bottom };
      top = bottom + 8;
      return compartment;
    });
  }

  function drawUmlFrame(frame, singleRoot) {
    const box = frame.bounds;
    const frameKind = frame.kind || "package";
    const group = el("g", {
      class: `node uml-frame${singleRoot && !frame.parent ? " package-overview" : ""}`,
      tabindex: "0", role: "button", "data-uml-id": frame.id, "data-uml-kind": frameKind,
      "data-label": frame.label,
    });
    group.appendChild(el("rect", { class: "target-frame", x: String(box.left),
      y: String(box.top), width: String(box.right - box.left),
      height: String(box.bottom - box.top), rx: "8" }));
    group.appendChild(el("rect", { class: "target-frame-header-hit", x: String(box.left),
      y: String(box.top), width: String(box.right - box.left),
      height: String(box.header), rx: "8" }));
    group.appendChild(el("path", { class: "uml-package", "aria-hidden": "true",
      d: `M${box.left + 14},${box.top + 15} h12 l4,5 h16 v18 h-32 z` }));
    const name = compactFrameName(frame.scope, box.right - box.left - 70);
    frameHeaderText(group, frameKind === "component" ? "«component»" : "«package»",
      name, box.left + 56, box.top + 37);
    group.setAttribute("aria-label", frame.tooltip);
    const title = el("title");
    title.textContent = frame.tooltip;
    group.appendChild(title);
    return group;
  }

  function drawUmlEdge(edge, route) {
    edge.routingWarning = Boolean(route.routingWarning);
    const warning = edge.routingWarning ? ` ${ROUTING_WARNING}` : "";
    const group = el("g", { class: `edge ${edge.state}${edge.edgeClass ? ` ${edge.edgeClass}` : ""}`, "data-uml-id": edge.id,
      "data-uml-kind": edge.kind, "data-uml-source": edge.source, "data-uml-target": edge.target });
    const line = el("path", { class: "line", d: route.d, "stroke-width": "2",
      ...(edge.state !== "declared" ? dashFor(edge.state, 2) : {}) });
    const title = el("title");
    title.textContent = edge.tooltip + warning;
    line.appendChild(title);
    const hit = el("path", { class: "hit", d: route.d, tabindex: "0", role: "button",
      "aria-label": edge.tooltip + warning,
      ...(route.routingWarning ? { "data-route-warning": "header-overlap" } : {}) });
    hit.appendChild(title.cloneNode(true));
    group.appendChild(line);
    if (edge.state !== "declared") group.appendChild(el("path", { class: "pulse", d: route.d }));
    group.appendChild(hit);
    if (edge.relationshipKind) {
      group.classList.add("architecture-edge");
      group.dataset.relationshipKind = edge.relationshipKind;
      line.style.strokeDasharray = edge.relationshipKind === "inherits" ? "none" : "6 4";
      if (["inherits", "realizes"].includes(edge.relationshipKind)) {
        line.style.markerEnd = "url(#uml-triangle)";
      } else if (!["violation", "undecided"].includes(edge.state)
        && svg.querySelector(`#flow-arrow-uml-${edge.relationshipKind}`)) {
        line.style.markerEnd = `url(#flow-arrow-uml-${edge.relationshipKind})`;
      } else if (edge.state === "declared") line.style.markerEnd = "url(#flow-arrow-declared)";
    }
    return { group, line, hit };
  }

  function renderUmlScene(scene, bindings, preparedRoutes = null) {
    renderedScene = scene;
    frameLayer.textContent = "";
    nodeLayer.textContent = "";
    edgeLayer.textContent = "";
    chipLayer.textContent = "";
    const singleRoot = scene.frames.filter((frame) => !frame.parent).length === 1;
    for (const frame of scene.frames) {
      const group = drawUmlFrame(frame, singleRoot);
      frameLayer.appendChild(group);
      bindings.frame(group, frame);
    }
    const layoutRoutes = preparedRoutes || REPORT_LAYOUT.routeUmlRelationships({
      positions,
      nodeSizes: Object.fromEntries(scene.nodes.map((node) => [node.id, { width: CARD.w, height: cardHeight(node.id) }])),
      edges: scene.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target,
        relationshipKind: edge.relationshipKind })),
      frames: Object.fromEntries(scene.frames.map((frame) => [frame.id, frame.bounds])),
      cardWidth: CARD.w, gap: GAP, laneGap: LANE_GAP, rowGap: ROW_GAP,
    });
    const edgeById = new Map(scene.edges.map((edge) => [edge.id, edge]));
    const routes = layoutRoutes.map((route) => ({ ...route,
      edge: route.edge || edgeById.get(route.edgeId) }));
    renderedRoutes = routes;
    for (const route of routes) {
      const drawn = drawUmlEdge(route.edge, route);
      edgeLayer.appendChild(drawn.group);
      Object.assign(route, drawn);
      bindings.edge(drawn, route);
    }
    for (const node of scene.nodes) {
      if (!positions[node.id]) continue;
      const group = drawUmlCard(node);
      nodeLayer.appendChild(group);
      bindings.node(group, node);
    }
    return routes;
  }

  function dashFor(state, width) {
    const ratio = DASH_RATIOS[state];
    if (!ratio) return {};
    return { "stroke-dasharray": ratio.map((part) => (part * width).toFixed(2)).join(" ") };
  }

  function emphasizeUmlScene(focus, previewing = false) {
    if (!renderedScene) return;
    const related = new Set(focus?.type === "node" ? [focus.id] : []);
    const active = new Set();
    renderedScene.edges.forEach((edge) => {
      if (!focus || (focus.type === "edge" ? edge.id === focus.id
          : [edge.source, edge.target].includes(focus.id))) {
        active.add(edge.id);
        related.add(edge.source);
        related.add(edge.target);
      }
    });
    nodeLayer.querySelectorAll("[data-uml-id]").forEach((node) => {
      node.classList.toggle("dim", Boolean(focus && !related.has(node.dataset.umlId)));
      node.classList.toggle("related", Boolean(focus && related.has(node.dataset.umlId)));
      node.classList.toggle("preview", previewing && focus?.type === "node" && focus.id === node.dataset.umlId);
    });
    edgeLayer.querySelectorAll("[data-uml-id]").forEach((node) => {
      node.classList.toggle("dim", !active.has(node.dataset.umlId));
      node.classList.toggle("related", Boolean(focus && active.has(node.dataset.umlId)));
      node.classList.toggle("preview", Boolean(previewing && focus && active.has(node.dataset.umlId)));
    });
    chipLayer.querySelectorAll(".chip").forEach((node) => {
      node.classList.toggle("dim", !active.has(node.dataset.key));
    });
  }
