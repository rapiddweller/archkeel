# AD-301 Studio keeps Briefing status and diagnostics scannable

**Status.** Accepted. Issue #831. Builds on AD-290 and AD-298.

**Decision.**
1. Briefing shows a short status and next step for failed, incomplete, and running Explore states. Report and Stories use the same failed state.
2. Repeated diagnostic notes show one row with a count. Failed-state notes stay available in collapsed details on all three pages.
3. An incomplete snapshot asks users to inspect its notes. Its UNKNOWN call count stays visible when a graph exists.
4. A failed or missing graph shows no measured facts or pass state. A failed Explore asks users to fix the cause and restart Studio.

**Reason.** A long diagnostic paragraph hides the state and the next action. Users need the summary before the details.

**Rejected.** Show every note in the first paragraph; hide diagnostics behind a status with no count; claim an incomplete scan will rerun or refresh.

**Limits.** Notes group only when their text matches exactly. A missing graph has no measured UNKNOWN count to show.

**Checks.** `tests/test_studio_browser.py` at 800×600 and 1440×900.
