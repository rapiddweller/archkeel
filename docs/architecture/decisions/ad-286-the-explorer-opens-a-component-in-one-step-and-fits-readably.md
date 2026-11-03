# AD-286 The Explorer opens a component in one step and fits it readably

**Status.** Accepted. Issue #782. Amends AD-264: Details no longer starts open.

**Decision.**
- Search opens a component. Its diagram shows in the current view (As-Is, Target or Diff). The URL
  carries `scope=<component id>` and `view=<view>`, as a click on a node already does.
  The Explorer scrolls to the top of the window, and focus moves to the first card once the
  level is drawn (to the current crumb when the level has no card).
  A full path, such as `io/data_sources/loaders/rdbms`, finds the component. An exact path ranks first.
- The Objects list keeps selecting a component among its siblings. It does not open it.
- The Atlas never fits below 90 %. The smallest card text is 13 px tall (bounding box) at 100 %, so
  it stays above 11 px. A level that needs more room scrolls. Zoom out stays free.
  The Fit button and its shortcut are named "Fit to window", not "Fit whole diagram".
- Details starts closed. A selection opens it: a click on a node, an edge or a finding,
  or `selected`, `module` or `cell` in the URL.
- The breadcrumb keeps the current level in view. Every crumb jumps to its level.

**Reason.** In an 800x600 pane the fit shrank a level of 11 components to 24 %, with text 3 px
tall. The Details panel took 280 px of 776. A component four levels deep needed several clicks.

**Rejected.**
- A floor of 100 %: the Atlas maximum is 100 %, so Fit would never scale.
- A lower floor: text under 11 px is not readable.
- Details open on wide screens only: two behaviours, and the 800x600 case is the one that fails.
- A second search field outside the dialog: the dialog already does the job.

**Limits.**
- The inventory of AD-264 lives in Details, so it is no longer on the first screen. Issue #791
  moves it into its own first-screen panel. Until then the Details button shows it.
- Fit on a map of modules no longer shows the whole map at once. Zoom out shows it.
- A level without edges lays out as one column and scrolls vertically.
- The 11 px bound comes from the text bounding box. Font metrics differ by platform, so the
  tests ran on macOS Chromium only.

**Check.**
- `tests/test_report_explorer_reach.py`: search opens `rdbms` in each view with scope and view in the URL;
  a full path finds it; Fit keeps all card text at 11 px or more at 800x600 and the level scrolls;
  Details is closed on first load and opens on a selection; breadcrumbs jump to any level.
- `tests/test_report_first_screen.py` opens Details before it reads the inventory.
- `make browser-runtime-check` passes with the regenerated runtime files.
