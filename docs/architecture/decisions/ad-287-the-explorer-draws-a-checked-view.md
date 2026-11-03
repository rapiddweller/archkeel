# AD-287 The Explorer draws a checked view

**Status.** Accepted. Issue #786, epic #783. Builds on AD-284 and AD-286.

**Decision.**
1. `archkeel view show <spec> [--snapshot PATH] [--output DIR] [--strict] [--json]` runs the
   check of `view check` (same options, same result), then writes the Explorer report of that
   snapshot with the result embedded. `--output` is valid only with `show`.
   - Stdout is byte-identical to `view check`. Stderr gets one line:
     `archkeel view show: wrote <DIR>/architecture.report.html`.
   - Exit 0 and 1 write the pages: a missing reference must show. Exit 2 (invalid input,
     tampered or other snapshot) writes nothing.
   - DIR gets `architecture.report.html`, its detail pages and the snapshot copied as
     `architecture.json`. Default DIR: `$XDG_CACHE_HOME/archkeel/view/<first 16 hex of the
     source digest>/` (default `~/.cache`). A run removes detail pages it does not write.
     Nothing goes next to the spec or the snapshot. The pages come from `run_saved_report`
     and `render_architecture_pages`, the code of `report`; the page heading is the view title.
2. The main page embeds the check result JSON, the one format, in `<script id="view-check-data">`.
   The Explorer draws it only when its source digest is the page's; the CLI embeds only a check
   of the snapshot it renders.
3. URL: `flow=1` opens the checked flow, `step=<n>` selects step n. A page with an embedded view
   and no `view` parameter opens the flow. `view=` keeps As-Is, Target and Diff.
4. Visual language (status is always text and icon, never colour only):

   | Status | Edge | Mark |
   |---|---|---|
   | `proven` | solid, coloured by kind, label = kind | ✓ proven |
   | `declared` | long dash, the report's declared colour | ◆ declared (contract) |
   | `claim` | short dash, amber | ✎ author claim |
   | `unknown` | dotted, grey | ? unknown + reason |
   | `missing` | dash-dot, red | ✕ not in the code |

   Steps are numbered cards 1..n. Author notes carry an "Author" mark and are never findings.
   A line above the diagram always shows `limits[0]` of the result ("structure, not runtime order").
5. The inspector (Details) shows status, reason, kind, path, each evidence `file:line`, record
   id and evidence id, the snapshot digests and `snapshot_current`.
6. Layout: one card for each step, keyed by its index, in one column in step order, at 100 %
   (AD-286); other spec nodes in a second column; «component» or «module» on each card. The
   layout engine routes the edges.
7. No contract (`explore`, #791): the flow view prints no PASS and shows each status with its reason.
   Target controls stay as `explore` sets them; `declared_rules` cannot mark "no contract".
8. Keyboard: Tab reaches each step card in order, Enter opens the inspector, Esc closes it.

**Rejected.** `view check --html`: a check verb must not write files. A second renderer or a
new JavaScript source owner. ELK layout: it can reorder steps. An absolute path in the HTML.

**Limits.** One view a page. The cache folder repeats `explore` (#791): merge them. A path is not order.

**Checks.** `tests/test_cli_view_show.py`; `tests/test_report_checked_flow.py` (Chromium, local
until Full runs it); demo row `protocol-view-show` (`test_view_variant_produces_the_catalogued_statuses`).
