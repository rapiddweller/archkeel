# AD-287 The Explorer draws a checked view

**Status.** Accepted. Issue #786, epic #783. Builds on AD-284 and AD-286.

**Decision.**
1. `archkeel view show <spec> [--snapshot PATH] [--output DIR] [--strict] [--json]` runs the
   check of `view check` (same options, same result), then writes the Explorer report of that
   snapshot with the result embedded. `--output` is valid only with `show`.
   - Stdout is byte-identical to `view check`. Stderr gets one line:
     `archkeel view show: wrote <DIR>/architecture.report.html`.
   - Exit 0 and 1 write the pages, also for an incomplete scan: its gaps show as unknown.
     Exit 2 (invalid input, tampered or other snapshot) writes nothing. A snapshot without an
     Explorer prints the check, writes nothing, says "not drawn" on stderr and exits 2.
   - DIR gets `architecture.report.html`, its detail pages and the snapshot copied as
     `architecture.json`. Default DIR: `$XDG_CACHE_HOME/archkeel/view/<16 hex of the hash of
     both digests and the spec>/`. A run first removes the files it writes, also a link in
     their place. The pages come from `run_saved_report` and `render_architecture_pages`.
2. The main page embeds the check result JSON, the one format, in `<script id="view-check-data">`.
   The Explorer draws it only when its source digest is the page's.
3. URL: `flow=1` opens the checked flow, `step=<n>` selects step n. A page with an embedded view
   and no `view` parameter opens the flow. As-Is, Target, Diff, search and a finding leave it.
4. Visual language (status is always text and icon, never colour only):

   | Status | Edge | Mark |
   |---|---|---|
   | `proven` | solid, coloured by kind, label = kind | ✓ proven (a node: observed) |
   | `declared` | long dash, the report's declared colour | ◆ declared |
   | `claim` | short dash, amber | ✎ author claim |
   | `unknown` | dotted, grey | ? unknown, reason in Details |
   | `missing` | dash-dot, red | ✕ not in the code |

   A step card shows its step status; Details shows its node. Author notes carry an "Author"
   mark. A line above the diagram counts steps, edges and nodes and shows `limits[0]`. Beside
   the flow no PASS shows: Details calls the observation "complete".
5. Details shows status, reason, kind, path, each evidence `file:line`, record id and evidence
   id, the snapshot digests and `snapshot_current`, and lists every edge.
6. Layout: one card for each step in step order, at 100 % (AD-286); other nodes in a second
   column. An edge with the same node at both ends shows on that card.
7. No contract (AD-285): AD-285 hides Target and Diff by a style rule. Open: a typed target
   field in the page data would replace that rule.
8. Keyboard: Tab reaches each step card in order, Enter opens Details, Esc closes it.

**Rejected.** `view check --html`: a check verb must not write files. A second renderer or a
new JavaScript source owner. ELK layout: it can reorder steps. An absolute path in the HTML.

**Limits.** One view a page. Archkeel owns the files it writes in `--output`, as in `explore`.
The Explorer compares the source digest only. The command reads the snapshot three times.

**Checks.** `tests/test_cli_view_show.py`; `tests/test_report_checked_flow.py` (Chromium, local
until Full runs it); demo row `protocol-view-show` (`test_view_variant_produces_the_catalogued_statuses`).
