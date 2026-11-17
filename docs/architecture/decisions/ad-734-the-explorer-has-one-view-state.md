# AD-734 The Explorer has one view state

**Status.** Accepted. Part of #880, #1451 (Wave 2, E1). Step 1 (this record) is structural: no visible change. Steps 2 and 3 (the query model and the history policy) amend this record when they land.

**Reason.** The Explorer (`native/report/assets/explorer/flow.js`, `report-canvas.js`) kept its view state in loose variables: the view, the path of levels, the content (components or modules), the selected box, the selected import cell and module, the question hint, the open Details, the open drawer, overlay and popover, the perspective, the pinned tag, the theme and the expanded mode. Each handler changed some of them and then drew. No one place said what the state is, so no test or agent could read it, and the URL, the history and the drawn page could disagree.

**Decision.**
1. One object `S` in `flow.js` holds the view state: `view`, `path`, `content`, `selection`, `cell`, `module`, `hint`, `allHints`, `details`, `explore`, and the presentation choices of `report-canvas.js` (`perspective`, `pinnedTag`, `drawer`, `overlay`, `pop`), `theme` and `expanded`.
2. A user action is one `dispatch(action)`. Each `action.type` is one case of one `switch`; an unknown type throws. The DOM handles of a drawer, an overlay or a popover stay in `report-canvas.js`; their names are in `S`.
3. `report-canvas.js` reads `ArchkeelFlow.S` and changes it only through `ArchkeelFlow.dispatch({type: "present", ...})`. Their effects (badges, drawers) stay in `report-canvas.js`.
4. `S.theme` follows the `data-theme` of the page, also when the header switch sets it.

**Rejected.** A state library or a build step for the Explorer (the scripts are plain, hashed files of the page). One state per script (the URL needs all of it).

**Tests.** `tests/test_report_explorer_state.py` drives the page in a headless Chrome (harness `tests/explorer_support.py`): the start level, Back, a deep link, a click, a view switch, Details, a crumb, Escape, a perspective, a matrix cell, and opening a module. They pass before and after step 1.
