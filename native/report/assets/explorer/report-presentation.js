"use strict";
// ArchQ Explorer presents recorded evidence; it never computes verdicts.
// The presentation choices of the canvas (perspectives and the tag bar) and the export of the diagram.
(function () {
  function create({ F, A, root, html, SVGNS, PERSPECTIVES, h, s, S, present, tagBar, components, toast, modal }) {
    const PALETTE = ["var(--line-strong)", "var(--accent-text)", "var(--ink-muted)", "var(--accent-hover)", "var(--ink-subtle)", "var(--accent)", "var(--ink)", "var(--surface-3)"];
    const categorical = {};
    for (const [key, choice] of Object.entries(PERSPECTIVES)) {
      if (choice.colors) continue;
      const values = [...new Set(components.map((c) => choice.value({ component: c })).filter(Boolean))].sort();
      categorical[key] = Object.fromEntries(values.map((value, i) => [value, PALETTE[i % PALETTE.length]]));
    }
    const colorOf = (key, value) => (PERSPECTIVES[key].colors || categorical[key])[value] || "var(--ink-subtle)";
    const languageKey = (value) => ["python", "rust", "typescript", "dart"].includes(value?.toLowerCase())
      ? value.toLowerCase() : "other";
    const languageColor = (value) => `var(--lang-${languageKey(value)})`;
    const perspectiveColor = (key, value) => key === "language" ? languageColor(value) : colorOf(key, value);
    const languageNames = ["python", "rust", "typescript", "dart", "other"];
    const languageBadge = (value) => h("span", {
      class: "ak-language-badge", "data-language": languageKey(value),
    }, value);
    function sceneNode(id) { return (F.state().scene?.nodes || []).find((node) => node.id === id); }
    function applyPerspective() {
      const active = PERSPECTIVES[S.perspective];
      root.toggleAttribute("data-ak-perspective", Boolean(active));
      F.nodeLayer.querySelectorAll("[data-uml-id]").forEach((group) => {
        group.querySelector(".ak-tag")?.remove();
        group.querySelectorAll(".stereotype, .uml-icon").forEach((item) => item.removeAttribute("visibility"));
        delete group.dataset.akTag;
        group.style.removeProperty("--ex-tag");
        if (!active) return;
        const node = sceneNode(group.dataset.umlId);
        const value = node && active.value(node);
        if (!value) return;
        group.dataset.akTag = value;
        group.style.setProperty("--ex-tag", perspectiveColor(S.perspective, value));
        // The badge sits in the header row of the box, left of its kind icon (icon at CARD.w - 29).
        // It is as wide as its text and never cut. A badge that does not fit beside the icon starts
        // at the left edge of the row and takes the place of the kind text and the icon; a value
        // wider than the whole row (16 to CARD.w - 7) is set in a smaller font.
        const tag = s("g", {
          class: S.perspective === "language" ? "ak-tag ak-language-badge" : "ak-tag",
          ...(S.perspective === "language" ? { "data-language": languageKey(value) } : {}),
        });
        const rect = s("rect", { height: "18", rx: "9" });
        const text = s("text", { x: "6", y: "13" });
        text.textContent = value;
        tag.append(rect, text);
        group.append(tag);
        const measure = () => Math.ceil(text.getComputedTextLength() || value.length * 6.6);
        const row = 200 - 16 - 7;
        if (measure() + 12 > row) {
          const size = parseFloat(getComputedStyle(text).fontSize) || 11;
          text.style.fontSize = `${Math.floor(size * (row - 12) / measure() * 10) / 10}px`;
        }
        const width = measure() + 12;
        const left = width <= 171 - 5 - 16 ? 171 - 5 - width : 16;
        rect.setAttribute("width", String(width));
        tag.setAttribute("transform", `translate(${left} 7)`);
        const kind = group.querySelector(".stereotype");
        if (kind && 16 + kind.getComputedTextLength() + 6 > left) kind.setAttribute("visibility", "hidden");
        if (left + width > 171 - 5) group.querySelector(".uml-icon")?.setAttribute("visibility", "hidden");
      });
      if (S.pinnedTag && (!active || !(F.state().scene?.nodes || []).some((node) => active.value(node) === S.pinnedTag))) present({ pinnedTag: null });
      highlightTag(S.pinnedTag);
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
      const active = PERSPECTIVES[S.perspective];
      const choices = [["", "None"], ...Object.entries(PERSPECTIVES).map(([key, item]) => [key, item.label])];
      const counts = new Map();
      if (active) for (const node of F.state().scene?.nodes || []) {
        const value = active.value(node);
        if (value) counts.set(value, (counts.get(value) || 0) + 1);
      }
      tagBar.replaceChildren(...[
        h("span", { class: "ak-tagbar-label" }, "Perspective"),
        ...choices.map(([key, label]) => h("button", { "data-focus-key": `perspective:${key}`, "aria-pressed": String((S.perspective || "") === key),
          onclick: () => { present({ perspective: key || null, pinnedTag: null }); applyPerspective(); } }, label)),
        active ? h("span", { class: "ak-sep" }) : null,
        ...(active ? [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).map(([value, count]) =>
          h("button", {
            class: S.perspective === "language" ? "ak-chip ak-language-badge" : "ak-chip",
            ...(S.perspective === "language" ? { "data-language": languageKey(value) } : {}),
            "data-focus-key": `tag:${value}`, style: `--chip:${perspectiveColor(S.perspective, value)}`, "aria-pressed": String(S.pinnedTag === value),
            title: `Highlight ${value}`, "aria-label": `${value}, ${count}`,
            onpointerenter: () => highlightTag(value), onpointerleave: () => highlightTag(S.pinnedTag),
            onclick: () => { present({ pinnedTag: S.pinnedTag === value ? null : value }); highlightTag(S.pinnedTag); renderTagBar(); } },
            h("i"), value, h("b", {}, String(count)))) : []),
        active && !counts.size ? h("span", { class: "ak-tagbar-label" }, "No tagged objects on this diagram") : null,
        // AD-606: a run of one part says so next to its language.
        S.perspective === "language" && A.language_note
          ? h("span", { class: "ak-tagbar-label", title: A.language_note }, "one part of the system: see the legend") : null,
      ].filter(Boolean));
      if (focusKey) [...tagBar.querySelectorAll("button")].find((button) => button.dataset.focusKey === focusKey)?.focus({ preventScroll: true });
    }
    function cyclePerspective() {
      const keys = [null, ...Object.keys(PERSPECTIVES)];
      present({ perspective: keys[(keys.indexOf(S.perspective) + 1) % keys.length], pinnedTag: null });
      applyPerspective();
    }

    async function copy(text, done) {
      try { await navigator.clipboard.writeText(text); toast(done); }
      catch { const area = h("textarea", { readonly: true }, text); modal([h("h2", {}, "Copy manually"), area], undefined, "copy"); area.select(); }
    }
    const mermaid = () => window.ArchkeelReportScene.sceneToMermaid(F.state().scene);
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
      clone.style.background = getComputedStyle(html).getPropertyValue("--surface-0");
      const blob = new Blob([new XMLSerializer().serializeToString(clone)], { type: "image/svg+xml" });
      const link = h("a", { href: URL.createObjectURL(blob), download: `${A.repository}-${F.state().viewMode}-${F.state().scope || "system"}.svg` });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      toast("SVG download started");
    }
    return { applyPerspective, renderTagBar, cyclePerspective, colorOf, languageNames, languageBadge, copy, mermaid, downloadSvg };
  }
  window.ArchkeelReportPresentation = { create };
})();
