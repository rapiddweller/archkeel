import { button, cards, element, get, showError, svgElement } from "./studio-dom.js";
import { api } from "./studio-api.js";
import { known, state } from "./studio-state.js";
import { open, select } from "./explorer.js";
import { derivedMapGroup } from "./explorer-map.js";
import { panMapTo } from "./explorer-map-layout.js";
import { canOpenScope } from "./explorer-uml.js";
const treeTypes = {
    layer: ["Layer", "M2 5l6-3 6 3-6 3z M2 8l6 3 6-3 M2 11l6 3 6-3"],
    component: ["Component", "M5 2h9v12H5 M2 4h6v3H2z M2 9h6v3H2z"],
    directory: ["Folder", "M1.5 4h5l2 2h6v7h-13z M1.5 4v-2h5l2 2h6v2"],
    module: ["Module", "M3 2h7l3 3v9H3z M10 2v3h3 M5 8h6 M5 11h6"],
    file: ["File", "M3 2h7l3 3v9H3z M10 2v3h3"],
    class: ["Class", "M2 2h12v12H2z M2 6h12 M2 10h12"],
    function: ["Function", "M5 13l2-9c.4-2 2-2.5 4-1 M4 7h7"],
    method: ["Method", "M2 11V5l4 4 4-4v6 M12 10l2 2 1-2"],
    property: ["Property", "M4 13V3h5a3 3 0 010 6H4"],
    interface: ["Interface", "M8 13v-4 M5 6a3 3 0 106 0 3 3 0 10-6 0z"],
};
const treeExpansion = new Map();
let treeDescription = 0;
function treeGlyph(parent, path, className) {
    const svg = svgElement("svg", { class: className, viewBox: "0 0 16 16", "aria-hidden": "true" }, parent);
    svgElement("path", { d: path }, svg);
}
export function treeMapAnchor(id) {
    const visible = new Map([...cards.querySelectorAll("[data-element]")].map((node) => [node.dataset.element, node]));
    const visited = new Set();
    for (let next = id; next && !visited.has(next); next = known.get(next)?.parent) {
        if (visible.has(next))
            return visible.get(next);
        visited.add(next);
    }
    return null;
}
export function markTreeSelection(id) {
    for (const node of get("structure-tree").querySelectorAll("button[data-tree-node]")) {
        const selected = node.dataset.treeNode === id;
        node.setAttribute("aria-pressed", String(selected));
        if (!selected)
            continue;
        for (let branch = node.closest(".tree-children"); branch; branch = branch.parentElement?.closest(".tree-children") ?? null) {
            if (branch.hidden)
                branch.parentElement?.querySelector(":scope > .tree-row .tree-disclosure")?.click();
        }
    }
}
function pickTreeNode(item) {
    const card = treeMapAnchor(item.id);
    const result = select(item);
    panMapTo(card);
    return result;
}
function treeBranch(scope, item, name, type, description, row, branch, seeded, byParent) {
    const prefix = scope + "\0" + item.id;
    const caption = name + " (" + type.toLowerCase() + ")";
    const toggle = button("", () => setExpanded(branch.hidden), "tree-disclosure");
    toggle.setAttribute("aria-describedby", description.id);
    branch.id = description.id + "-children";
    toggle.setAttribute("aria-controls", branch.id);
    treeGlyph(toggle, "M6 4l4 4-4 4", "tree-chevron");
    row.prepend(toggle);
    let loaded = Boolean(seeded?.length);
    let busy = false;
    const appendChildren = async (cursor = "") => {
        if (busy)
            return;
        busy = true;
        branch.setAttribute("aria-busy", "true");
        const pending = element("li", "Loading…", "tree-message");
        branch.append(pending);
        try {
            const args = { parent: item.id, limit: 24, cursor };
            const result = await (item.kind === "component" || derivedMapGroup(item)
                ? api("map", { ...args, view: derivedMapGroup(item) ? "hierarchy" : "components" })
                : api("children", args));
            if (!branch.isConnected)
                return;
            loaded = true;
            for (const child of [...(result.groups ?? []), ...result.items])
                known.set(child.id, child);
            appendTreeItems(scope, item.id, branch, treeByParent(result));
            const next = result.next_cursor;
            if (next) {
                const rest = element("li", "", "tree-message");
                rest.append(button("More children", () => {
                    rest.remove();
                    return appendChildren(next);
                }));
                branch.append(rest);
            }
            else if (!cursor && !result.items.length) {
                branch.append(element("li", "No indexed children", "tree-message"));
            }
        }
        catch {
            pending.replaceChildren(button("Retry loading children", () => {
                pending.remove();
                return appendChildren(cursor);
            }));
            return;
        }
        finally {
            busy = false;
            branch.removeAttribute("aria-busy");
            if (pending.textContent === "Loading…")
                pending.remove();
        }
    };
    function setExpanded(expanded) {
        branch.hidden = !expanded;
        treeExpansion.set(prefix, expanded);
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", (expanded ? "Collapse " : "Expand ") + caption);
        if (expanded && !loaded)
            return appendChildren();
    }
    row.addEventListener("keydown", (event) => {
        if (event.key === "ArrowRight") {
            event.preventDefault();
            if (branch.hidden)
                setExpanded(true);
            else
                branch.querySelector("button:not([disabled])")?.focus();
        }
        else if (event.key === "ArrowLeft") {
            event.preventDefault();
            if (!branch.hidden)
                setExpanded(false);
            else
                row.closest("ul")?.parentElement?.querySelector(":scope > .tree-row button")?.focus();
        }
    });
    if (seeded)
        for (const child of seeded)
            branch.append(treeItem(scope, child, byParent));
    const expanded = treeExpansion.get(prefix) ?? loaded;
    branch.hidden = !expanded;
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.setAttribute("aria-label", (expanded ? "Collapse " : "Expand ") + caption);
    if (expanded && !loaded)
        queueMicrotask(() => {
            if (branch.isConnected)
                setExpanded(true);
        });
}
function treeItem(scope, item, byParent) {
    const li = element("li", "", "tree-item");
    li.dataset.treeItem = item.id;
    const row = element("div", "", "tree-row");
    const filename = ["module", "file", "directory"].includes(item.kind) && item.path?.split("/").at(-1);
    const name = filename || item.display_name || item.name;
    const [type, outline] = treeTypes[item.kind] ?? ["Symbol", "M4 4h8v8H4z"];
    const hint = element("span", type + (item.path ? " · Source " + item.path : ""), "tree-kind-text");
    hint.id = "structure-type-" + ++treeDescription;
    const action = button("", () => pickTreeNode(item), "tree-select");
    action.title = item.path ?? item.name;
    action.setAttribute("aria-describedby", hint.id);
    action.dataset.treeNode = item.id;
    action.setAttribute("aria-pressed", String(state.selected === item.id));
    action.addEventListener("dblclick", () => open(item).catch(showError));
    treeGlyph(action, outline, "tree-type-glyph type-" + item.kind);
    action.append(element("span", name, "tree-node-name"));
    row.append(action, hint);
    li.append(row);
    const seeded = byParent.get(item.id);
    if (seeded?.length || canOpenScope(item)) {
        const branch = element("ul", "", "tree-children");
        li.append(branch);
        treeBranch(scope, item, name, type, hint, row, branch, seeded, byParent);
    }
    else {
        row.prepend(element("span", "", "tree-leaf-dot"));
        row.addEventListener("keydown", (event) => {
            if (event.key === "ArrowLeft") {
                event.preventDefault();
                li.parentElement?.parentElement?.querySelector(":scope > .tree-row button")?.focus();
            }
        });
    }
    return li;
}
function treeByParent(response) {
    const byParent = new Map();
    for (const item of [...(response.groups ?? []), ...response.items]) {
        const items = byParent.get(item.parent);
        if (items)
            items.push(item);
        else
            byParent.set(item.parent, [item]);
    }
    return byParent;
}
function appendTreeItems(scope, parent, list, byParent) {
    for (const item of byParent.get(parent) ?? []) {
        const existing = [...list.children].find((child) => child.getAttribute("data-tree-item") === item.id);
        const branch = existing?.querySelector(":scope > .tree-children");
        if (branch)
            appendTreeItems(scope, item.id, branch, byParent);
        else if (!existing)
            list.append(treeItem(scope, item, byParent));
    }
}
export function paintStructure(response) {
    const list = element("ul", "", "tree-root");
    appendTreeItems(response.parent, response.parent, list, treeByParent(response));
    get("structure-tree").replaceChildren(list);
}
