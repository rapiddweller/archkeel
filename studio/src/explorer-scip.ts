import { api } from "./studio-api.js";
import type { StudioItem } from "./studio-model.js";
import { state } from "./studio-state.js";
import { breakPath, element, button, details } from "./studio-dom.js";

interface CallResolutionCount {
  language: string;
  status: string;
  provenance: string | null;
  reason: string | null;
  count: number;
}

interface CallResolutionItem {
  call_id: string;
  relation_id: string;
  language: string;
  status: string;
  provenance: string | null;
  reason: string | null;
  canonical_target_definition_id: string | null;
  target_element_id: string | null;
  dispatch_kind: string | null;
  declaration_path: string | null;
  declaration_line: number | null;
  crate_name: string | null;
  crate_version: string | null;
  symbol_path: string | null;
  reference: { path: string; start_line: number; start_column: number; end_line: number; end_column: number } | null;
}

interface CallResolutionResponse {
  available: boolean;
  counts: CallResolutionCount[];
  items: CallResolutionItem[];
  next_cursor: string | null;
}

type Heading = (name: string, kind: string) => void;

function formatScipCounts(counts: CallResolutionCount[]): string {
  const totals: Record<string, number> = {};
  for (const row of counts) totals[row.status] = (totals[row.status] ?? 0) + row.count;
  const parts: string[] = [];
  for (const [key, label] of [
    ["local_resolved", "local"],
    ["external_std", "stdlib"],
    ["external_dep", "external crates"],
    ["unresolved", "open"],
  ] as const) {
    if (totals[key]) parts.push(totals[key].toLocaleString() + " " + label);
  }
  return "SCIP call evidence (separate from native AST): " + parts.join(" · ");
}

function entryTitle(entry: CallResolutionItem): string {
  const origin = entry.provenance ? " · " + entry.provenance : "";
  if (entry.status === "local_resolved") return "Local (" + (entry.dispatch_kind ?? "direct") + ")" + origin;
  if (entry.status === "external_std" || entry.status === "external_dep") {
    const version = entry.crate_version ? " " + entry.crate_version : "";
    return (entry.crate_name ?? entry.status) + version + " · " + (entry.symbol_path ?? "");
  }
  return "Open (" + (entry.reason ?? "unresolved") + ")" + origin;
}

function entryDetail(entry: CallResolutionItem): string {
  if (entry.declaration_path && entry.declaration_line) return "Target: " + entry.declaration_path + ":" + entry.declaration_line;
  if (entry.reference) return entry.reference.path + ":" + (entry.reference.start_line + 1);
  return entry.call_id;
}

async function openScip(item: StudioItem, request: number, heading: Heading, cursor = "", view = ++state.view) {
  const result = await api<CallResolutionResponse>("call_resolution", { element: item.id, cursor, limit: 30 });
  if (state.request !== request || state.view !== view) return;
  if (!cursor) {
    heading(item.name, "SCIP call evidence · separate from native AST");
    view = state.view;
    if (result.counts.length) details.append(element("p", formatScipCounts(result.counts), "meta"));
  }
  for (const entry of result.items) {
    const card = element("div", "", "detail-btn call-site");
    card.append(element("strong", entryTitle(entry)));
    card.append(breakPath(element("span", "", "meta"), entryDetail(entry)));
    details.append(card);
  }
  if (result.next_cursor) {
    const more = button("More SCIP call evidence", () => { more.remove(); return openScip(item, request, heading, result.next_cursor!, view); }, "detail-btn");
    details.append(more);
  }
}

export async function showScipSummary(
  item: StudioItem,
  request: number,
  view: number,
  slot: HTMLElement,
  heading: Heading,
) {
  try {
    const summary = await api<CallResolutionResponse>("call_resolution", { element: item.id, limit: 1 });
    if (state.request !== request || state.view !== view || !slot.isConnected || !summary.available || !summary.counts.length) return;
    slot.append(
      element("p", formatScipCounts(summary.counts), "meta"),
      button("Inspect SCIP call evidence", () => openScip(item, request, heading), "detail-btn"),
    );
  } catch {
    // Optional SCIP evidence must never disrupt the native inspector.
  }
}
