# AD-301 Studio keeps Briefing status and diagnostics scannable

**Status.** Accepted. Issue #831. Builds on AD-290 and AD-298.

**Decision.**
1. Briefing shows a short status and next step for failed, incomplete, and running Explore states.
2. Repeated diagnostic notes show one row with a count. The full notes stay available in a collapsed details section.
3. An incomplete graph keeps its UNKNOWN call count visible. A failed or missing graph does not show measured facts or a pass state.

**Reason.** A long diagnostic paragraph hides the state and the next action. Users need the summary before the details.

**Rejected.** Show every note in the first paragraph; hide diagnostics behind a status with no count.

**Limits.** Notes group only when their text matches exactly. A missing graph has no measured UNKNOWN count to show.

**Checks.** `tests/test_studio_browser.py` at 800×600 and 1440×900.
