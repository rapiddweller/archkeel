# AD-295 View checks name incomplete source and stories show checked counts

**Status.** Accepted. Issue #830; builds on AD-290 and AD-291.

**Decision.** View-check result schema 1.3.0 carries `result_schema_version` and
`snapshot_completeness`. Completeness is `complete` only when source coverage is PASS and has no
coverage failures. `view check`, `view show` and Studio warn on an incomplete snapshot; node and
step statuses remain as measured, including UNKNOWN. Studio API 1.2 adds checked status counts to
story-list rows. Counts are null until a finished snapshot can check that spec, including malformed
specs. A story endpoint on a failed explore returns 503 with its exit code and notes.

**Reason.** A nonzero exit does not say whether a usable snapshot exists, and missing evidence must
not become absence or a zero count.

**Rejected.** Inferring completeness from exit code, or counting an unchecked story as zero.

**Checks.** `tests/test_cli_story.py`, `tests/test_cli_view_show.py`, `tests/test_studio.py`.
