# AD-734 The Explorer has one view state

**Status.** Accepted. Part of #880, #1451 (Wave 2, E1). Step 1 (decisions 1 to 4) is structural: no visible change. Steps 2 and 3 (decisions 5 to 8) are visible: Back goes back one level, and a link keeps Details, the drawer and the perspective.

**Reason.** The Explorer (`native/report/assets/explorer/flow.js`, `report-canvas.js`) kept its view state in loose variables: the view, the path of levels, the content (components or modules), the selected box, the selected import cell and module, the question hint, the open Details, the open drawer, overlay and popover, the perspective, the pinned tag, the theme and the expanded mode. Each handler changed some of them and then drew. No one place said what the state is, so no test or agent could read it, and the URL, the history and the drawn page could disagree.

**Decision.**
1. One object `S` in `flow.js` holds the view state: `view`, `path`, `content`, `selection`, `cell`, `module`, `hint`, `allHints`, `details`, `explore`, and the presentation choices of `report-canvas.js` (`perspective`, `pinnedTag`, `drawer`, `overlay`, `pop`), `theme` and `expanded`.
2. A user action is one `dispatch(action)`. Each `action.type` is one case of one `switch`; an unknown type throws. The DOM handles of a drawer, an overlay or a popover stay in `report-canvas.js`; their names are in `S`.
3. `report-canvas.js` reads `ArchkeelFlow.S` and changes it only through `ArchkeelFlow.dispatch({type: "present", ...})`. Their effects (badges, drawers) stay in `report-canvas.js`.
4. `S.theme` follows the `data-theme` of the page, also when the header switch sets it.
5. `toQuery(S)` writes the URL of a state and `fromQuery(query)` reads the state of a URL: `scope`, `content`, `view`, `perspective`, `selected`, `cell`, `details`, `drawer`. A default is left out: the language perspective, Details that follow the selection (open with a selected box or cell, closed without), no drawer. `toQuery(fromQuery(q))` is `q` for each query that `toQuery` writes. `report-canvas.js` writes no URL of its own.
6. `data-state` on the Explorer holds the state as JSON (view, scope, path, content, selection, edge, module, cell, hint, details, drawer, overlay, pop, perspective, pinned tag, theme, expanded, notice). `ArchkeelFlow.state()` returns the same fields, and `ArchkeelFlow.dispatch`, `toQuery` and `fromQuery` are public to the page.
7. History: a navigation (open a level, go up, a crumb, set the view, set the content, open a module at another level) adds a history entry. Any other change (a selection, a cell, Details, the drawer, the perspective, the theme) replaces the current entry. So Back goes back one level, not one click.
8. A deep link restores the selection, Details, the drawer and the perspective. Details stay open at the start when the link selects a box or a cell (the report no longer closes them at the start).

**Rejected.** A state library or a build step for the Explorer (the scripts are plain, hashed files of the page). One state per script (the URL needs all of it).

**Tests.** `tests/test_report_explorer_state.py` drives the page in a headless Chrome (harness `tests/explorer_support.py`): the start level, Back, a deep link, a click, a view switch, Details, a crumb, Escape, a perspective, a matrix cell, and opening a module. They pass before and after step 1. Steps 2 and 3 add tests that failed first: Back after two selections goes back one level, a deep link restores Details, the drawer and the perspective, and the URL of a state gives the same state back.
