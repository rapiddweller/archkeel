# AD-286 The Explorer opens a component in one step and reads at 100 %

**Status.** Accepted. Issue #782. Amends AD-264: Details no longer starts open.

**Decision.**
- Search opens a component. Its diagram shows in the current view (As-Is, Target or Diff). The URL
  carries `scope=<component id>` and `view=<view>`, as a click on a node already does.
  A full path, such as `io/data_sources/loaders/rdbms`, or a source path, such as
  `src/archkeel/render`, ranks that component before its children.
- The Explorer scrolls to the top of the window. Whenever a level opens (search, Enter on a card,
  a crumb), focus moves to its first card once the level is drawn. Without a card it moves to the
  current crumb. A later render cancels a pending focus.
- The Objects list keeps selecting a component among its siblings. It does not open it.
- A component diagram never fits below 100 %, so its card text is 11 px or more. A level that
  needs more room scrolls from the top. Zoom out stays free. Shift C (zoom to selection) stays at 100 %.
- On a map of modules the button keeps its one-click overview: it shows the whole map, below 100 %.
- The control is named "Reset zoom", in the button and in the Shortcuts list.
- Details starts closed. A selection opens it: a click on a node, an edge or a finding, or
  `selected`, `module` or `cell` in the URL. On the detail page a requested `module` opens it.
- The breadcrumb keeps the current level in view. Every crumb jumps to its level.

**Reason.** In an 800x600 pane the fit shrank a level of 11 components to 24 %, with text 3 px
tall. The Details panel took 280 px of 776. A component four levels deep needed several clicks.

**Rejected.**
- A floor of 90 %: the glyph box measures 11 px, but the font size is 9.9 px. The reader needs the
  font size, so every lower floor is rejected for component diagrams.
- Details open on wide screens only: two behaviors, and 800x600 is the case that fails.
- A second search field outside the dialog: the dialog already does the job.

**Limits.**
- The inventory of AD-264 lives in Details, so it is not on the first screen. A first-screen
  panel is planned (#791). Until then the Details button shows it.
- A level without edges lays out as one column. It scrolls vertically and leaves the sides empty,
  also at 1440x900.
- With a deep path the first crumb can be cut at the left edge. Scroll the trail or use "Belongs to".
- "Reset zoom" on a module map shows the whole map, not 100 %.

**Check.**
- `tests/test_report_explorer_reach.py`: search opens `rdbms` in each view with scope and view in
  the URL; a full path and a source path find a component; focus lands in the new level after search
  and after Enter on a card; Reset zoom and Shift C keep the font at 11 px or more (computed font
  size times the SVG scale) at 800x600 while the level scrolls from the top; a module map still
  fits whole; Details is closed on first load and opens on a selection, on `module` and on `cell`
  in the URL, and on a requested `module` on the detail page; breadcrumbs jump to any level.
- `tests/test_report_renderer_units.py`: an exact label or source path ranks first.
- `tests/test_report_first_screen.py` opens Details before it reads the inventory.
- The Chromium tests run locally (`make report-browser-tests`) until they join Full verification.
- `make browser-runtime-check` passes with the regenerated runtime files.
