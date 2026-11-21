import { api } from "./studio-api.js";
import { state } from "./studio-state.js";
import { breakPath, element, button, details } from "./studio-dom.js";
function formatScipCounts(counts) {
    const totals = {};
    for (const row of counts)
        totals[row.status] = (totals[row.status] ?? 0) + row.count;
    const parts = [];
    for (const [key, label] of [
        ["local_resolved", "local"],
        ["external_std", "stdlib"],
        ["external_dep", "external crates"],
        ["unresolved", "open"],
    ]) {
        if (totals[key])
            parts.push(totals[key].toLocaleString() + " " + label);
    }
    return "SCIP call evidence (separate from native AST): " + parts.join(" · ");
}
function entryTitle(entry) {
    const origin = entry.provenance ? " · " + entry.provenance : "";
    if (entry.status === "local_resolved")
        return "Local (" + (entry.dispatch_kind ?? "direct") + ")" + origin;
    if (entry.status === "external_std" || entry.status === "external_dep") {
        const version = entry.crate_version ? " " + entry.crate_version : "";
        return (entry.crate_name ?? entry.status) + version + " · " + (entry.symbol_path ?? "");
    }
    return "Open (" + (entry.reason ?? "unresolved") + ")" + origin;
}
function entryDetail(entry) {
    if (entry.declaration_path && entry.declaration_line)
        return "Target: " + entry.declaration_path + ":" + entry.declaration_line;
    if (entry.reference)
        return entry.reference.path + ":" + (entry.reference.start_line + 1);
    return entry.call_id;
}
async function openScip(item, request, heading, cursor = "", view = ++state.view) {
    const result = await api("call_resolution", { element: item.id, cursor, limit: 30 });
    if (state.request !== request || state.view !== view)
        return;
    if (!cursor) {
        heading(item.name, "SCIP call evidence · separate from native AST");
        view = state.view;
        if (result.counts.length)
            details.append(element("p", formatScipCounts(result.counts), "meta"));
    }
    for (const entry of result.items) {
        const card = element("div", "", "detail-btn call-site");
        card.append(element("strong", entryTitle(entry)));
        card.append(breakPath(element("span", "", "meta"), entryDetail(entry)));
        details.append(card);
    }
    if (result.next_cursor) {
        const more = button("More SCIP call evidence", () => { more.remove(); return openScip(item, request, heading, result.next_cursor, view); }, "detail-btn");
        details.append(more);
    }
}
export async function showScipSummary(item, request, view, slot, heading) {
    try {
        const summary = await api("call_resolution", { element: item.id, limit: 1 });
        if (state.request !== request || state.view !== view || !slot.isConnected || !summary.available || !summary.counts.length)
            return;
        slot.append(element("p", formatScipCounts(summary.counts), "meta"), button("Inspect SCIP call evidence", () => openScip(item, request, heading), "detail-btn"));
    }
    catch {
        // Optional SCIP evidence must never disrupt the native inspector.
    }
}
