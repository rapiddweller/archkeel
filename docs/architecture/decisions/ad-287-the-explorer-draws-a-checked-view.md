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
     source digest>/` (default `~/.cache`). A run first removes its old files there. Nothing
     goes next to the spec or the snapshot. The pages come from `run_saved_report` and
     `render_architecture_pages`, the code of `report`.
2. The main page embeds the check result JSON, the one format, in `<script id="view-check-data">`.
   The Explorer draws it only when its source digest is the page's; the CLI embeds only a check
   of the snapshot it renders.
3. URL: `flow=1` opens the checked flow, `step=<n>` selects step n. A page with an embedded view
   and no `view` parameter opens the flow. `view=` keeps As-Is, Target and Diff.
4. Visual language (status is always text and icon, never colour only):

   | Status | Edge | Mark |
   |---|---|---|
   | `proven` | solid, coloured by kind, label = kind | ✓ proven |
   | `declared` | long dash, gold | ◆ declared (contract) |
   | `claim` | short dash, amber | ✎ author claim |
   | `unknown` | dotted, grey | ? unknown + reason |
   | `missing` | dash-dot, red | ✕ not in the code |

   Steps are numbered cards 1..n. Author notes carry an "Author" mark and are never findings.
   The summary line always shows `limits[0]` of the result ("structure, not runtime order").
5. The inspector (Details) shows status, reason, kind, path, each evidence `file:line`, record
   id and evidence id, the snapshot digests and `snapshot_current`.
6. Layout: one card for each step, keyed by its index, in one column in step order, at 100 %
   (AD-286); other spec nodes in a second column; «component» or «module» on each card. The
   layout engine routes the edges.
7. No contract (AD-285): the flow view prints no PASS and shows each status with its reason.
   When the page's `declared_rules` is `UNKNOWN`, the flow view disables Target and Diff.
8. Keyboard: Tab reaches each step card in order, Enter opens the inspector, Esc closes it.

**Rejected.** `view check --html`: a check verb must not write files. A second renderer or a
new JavaScript source owner. ELK layout: it can reorder steps. An absolute path in the HTML.

**Limits.** One view a page. The cache folder repeats AD-285: merge the helpers. A path is not order.

**Checks.** Planned: `tests/test_cli_view_show.py`, `tests/test_report_checked_flow.py`
(browser), demo row `protocol-view-show`.
