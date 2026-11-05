# AD-298 Studio keeps a readable incomplete snapshot

**Status.** Accepted for issue #828, step 1. Builds on AD-290 and API 1.2.

**Decision.**
1. Explore exit 2 with a readable `architecture.json` gives Studio state `incomplete`.
   Studio keeps the diagnostics and exposes the measured graph. UNKNOWN calls stay UNKNOWN.
   Story checks and counts may use it: checks report `snapshot_completeness: incomplete` and
   preserve UNKNOWN. The Stories and report pages label the limitation.
2. Exit 0 also needs a readable snapshot. A missing or invalid snapshot gives `failed` and no graph.
   Other non-zero exits remain `failed`, even if a snapshot exists.
   Each restart removes the previous snapshot before launching Explore.
3. API 1.3 adds the `incomplete` state. API 1.2 and its schema stay unchanged.
   The first page labels the snapshot incomplete and shows its notes. Drafting and chat remain
   unavailable because their responses do not carry a completeness label.

**Reason.** Exit 2 can mean that analysis is incomplete, not that it produced no data. A valid
snapshot remains useful when the UI preserves its UNKNOWN calls and shows the diagnostics.

**Rejected.** Treat every non-zero exit as failed; expose any snapshot without validating it.

**Limits.** Only exit 2 is treated as incomplete. Studio does not retry a failed or incomplete run.

**Checks.** `tests/test_studio.py`, `tests/test_studio_browser.py`.
