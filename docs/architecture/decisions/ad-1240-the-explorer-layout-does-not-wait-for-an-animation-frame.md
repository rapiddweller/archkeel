# AD-1240 The Explorer layout does not wait for an animation frame

**Status.** Accepted. Issue #2126.

**Reason.** `report-placement.js` waited for `requestAnimationFrame` before it ran ELK, so that the canvas could paint its notice "Arranging ...". A page that gets no frame (a throttled tab, a headless Chrome under load) never resolved the wait. The root stayed `data-layout-state="pending"`, the diagram never arranged, and `test_the_explorer_starts_on_each_page[shell]` failed intermittently on main CI.

**Decision.** The wait ends on the first of two events: the frame (then one timer tick, as before), or a timer of 100 ms. A hidden page or a browser without `requestAnimationFrame` still skips the wait.

**Rejected.**
- A longer test budget or a retry: the wait has no end without a frame, so a budget does not help and a retry hides the defect.
- No wait at all: the notice would not paint before the layout blocks the thread.

**Limit.** A page that gets its first frame later than 100 ms starts the layout before the notice is painted. The result is the same diagram; only the notice may not show. The CI trigger of the original failure is Likely (a page without frames), not proven; the stub test proves the failure signature.

**Tests.** `tests/test_report_page_scripts.py::test_the_explorer_arranges_when_the_page_never_gets_an_animation_frame` stubs `requestAnimationFrame` before the page scripts and asserts `ready`. With the old script it stays `pending`.
