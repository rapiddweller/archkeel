import { button, cards, element, get, showError } from "./studio-dom.js";
import { api } from "./studio-api.js";
import type { Page } from "./studio-api.js";
import type { StudioItem } from "./studio-model.js";
import { known, pageTrails, state, system } from "./studio-state.js";
import { drawArrows, open, select } from "./explorer.js";

const umlOrder: Record<string, number> = { component: 0, module: 1, class: 2, property: 3, method: 4, interface: 5, function: 6 };
const umlNames = new Intl.Collator("en", { numeric: true, sensitivity: "base" });
const umlGlyphs: Record<string, string> = {
  component: "M7 2h14v20H7v-5 M7 12v-2 M7 5V2 M3 5h8v5H3z M3 12h8v5H3z",
  module: "M5 2h9l5 5v15H5z M14 2v5h5",
  class: "M3 2h18v20H3z M3 9h18 M3 15h18",
  interface: "M12 15v7 M17 9a5 5 0 1 1-10 0 5 5 0 0 1 10 0",
};

function umlGlyph(outline: string) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.classList.add("uml-glyph");
  const path = document.createElementNS(svg.namespaceURI, "path");
  path.setAttribute("d", outline);
  svg.append(path);
  return svg;
}

export function itemKind(item: StudioItem, observed = false) {
  if (item.kind === "component") return observed ? "Package group" : "Component";
  if (item.kind === "directory") return "Package group";
  if (item.kind === "file_group") return "File group";
  if (item.kind === "module") return "File";
  return item.kind;
}

export function canOpenScope(item: StudioItem) {
  return item.open_target ? item.open_target === "map" : ["component", "layer", "directory", "file_group", "module", "class"].includes(item.kind);
}

function displayGroup(item: StudioItem) {
  const current = state.ancestors.at(-1);
  if (item.kind === "module" && !state.search && current?.kind === "component") {
    const separator = item.name.lastIndexOf(".");
    if (separator > 0) return "Modules · " + item.name.slice(0, separator);
  }
  if (item.kind === "component") return item.id.startsWith("PART:") ? "System parts" : "Components";
  const kinds: Record<string, string> = {
    module: "Modules", class: "Classes", interface: "Interfaces",
    function: "Functions", method: "Methods", property: "Properties",
  };
  return kinds[item.kind] ?? "Other symbols";
}

function umlCompartment(title: string) {
  const compartment = element("span", "", "uml-compartment");
  compartment.append(element("span", title, "uml-compartment-title"),
    element("span", "Loading…", "uml-members"));
  return compartment;
}

async function loadClassCard(item: StudioItem, compartments: HTMLElement[]) {
  try {
    const { items, next_cursor: more } = await api<Page<StudioItem>>("children", { parent: item.id, limit: 24 });
    if (!compartments[0].isConnected) return;
    for (const [index, kind] of ["property", "method"].entries()) {
      const list = compartments[index].querySelector(".uml-members");
      if (!list) continue;
      const matches = items.filter((member) => member.kind === kind);
      const labels = new Map(matches.map((member) => {
        const name = member.display_name ?? member.name.split(".").at(-1) ?? member.name;
        const annotation = kind === "property" && member.annotation;
        return [name, annotation ? name + " : " + annotation : name];
      }));
      if (kind === "property") {
        for (const name of item.property_names ?? []) if (!labels.has(name)) labels.set(name, name);
      }
      const ordered = [...labels.values()].sort(umlNames.compare);
      list.replaceChildren(...ordered.slice(0, 4).map((label) =>
        element("span", label, "uml-member")));
      const coverage = item.member_coverage?.[kind] ?? (item.members_complete ? "complete" : "unknown");
      const note = coverage === "partial" ? "Partial coverage"
        : coverage === "unknown" ? "Coverage unknown"
        : !labels.size && !more ? "None recorded" : "";
      if (note) list.append(element("span", note, "uml-member-note" +
        (coverage === "complete" ? "" : " unknown")));
      if (labels.size > 4 || more) list.append(element("span", "Open class for more", "uml-member-note"));
    }
    drawArrows();
  } catch {
    for (const compartment of compartments) {
      const members = compartment.querySelector(".uml-members");
      if (members) members.textContent = "Member data unavailable";
    }
  }
}

function umlTitle(item: StudioItem) {
  return item.display_name ?? (item.kind === "class" ? item.name.split(".").at(-1) ?? item.name : item.name);
}

export function umlCard(item: StudioItem) {
  const language = ["rust", "python", "typescript", "dart"].includes(item.language ?? "") ? item.language : "";
  const card = button("", () => select(item), "card uml-card " + language);
  card.dataset.element = item.id;
  card.dataset.umlKind = item.kind;
  card.setAttribute("aria-pressed", String(item.id === state.selected));
  card.setAttribute("aria-label", [item.kind, language, item.name].filter(Boolean).join(" · "));
  const head = element("span", "", "uml-head");
  const stereotype = item.kind === "component" ? "«component»" : item.kind;
  head.append(element("span", [stereotype, language].filter(Boolean).join(" · "), "uml-stereotype"),
    element("strong", umlTitle(item), "uml-name"));
  card.title = item.name;
  const outline = umlGlyphs[item.kind];
  if (outline) head.append(umlGlyph(outline));
  const purpose = item.kind === "component" && item.responsibilities?.[0];
  if (purpose) head.append(element("span", purpose, "uml-purpose"));
  card.append(head);
  if (item.kind === "class") {
    const compartments = ["Properties", "Methods"].map(umlCompartment);
    card.append(...compartments);
    loadClassCard(item, compartments);
  }
  card.addEventListener("dblclick", () => open(item).catch(showError));
  card.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    open(item).catch(showError);
  });
  return card;
}

export function paintCards() {
  cards.replaceChildren();
  const groups = new Map<string, HTMLButtonElement[]>();
  const ordered = state.items.slice().sort((a, b) =>
    (umlOrder[a.kind] ?? 99) - (umlOrder[b.kind] ?? 99)
    || umlNames.compare(displayGroup(a), displayGroup(b))
    || umlNames.compare(umlTitle(a), umlTitle(b))
    || a.id.localeCompare(b.id));
  for (const item of ordered) {
    known.set(item.id, item);
    const group = displayGroup(item);
    const children = groups.get(group);
    const card = umlCard(item);
    if (children) children.push(card);
    else groups.set(group, [card]);
  }
  for (const [name, children] of groups) {
    const plate = element("section", "", "plate");
    const grid = element("div", "", "plate-grid");
    grid.append(...children);
    plate.append(element("h3", name), grid);
    cards.append(plate);
  }
  if (!state.items.length) {
    const isModule = !state.search && state.ancestors.at(-1)?.kind === "module";
    cards.append(element("p", isModule ? "No symbol records for this module. Open source to inspect its declarations."
      : "No indexed elements in this scope."));
  }
  get("previous").hidden = (pageTrails.get(state.ancestors.at(-1)?.id ?? system.id)?.length ?? 0) <= 1;
  get("more").hidden = !state.cursor;
  drawArrows();
}
