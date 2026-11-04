# AD-296 Traces display source labels and keep canonical names

**Status.** Accepted. Issue #830; builds on AD-291.

**Decision.** Story-trace schema 1.1 adds a readable `label` beside each canonical node `name`.
The label uses the existing definition path, line and symbol suffix after removing the known module
prefix; it never decodes escaped IDs. `view check` story steps carry the same label, and the CLI and
Studio display it while references and stored specs keep the canonical name. Missing source
locations fall back to the canonical name.

**Reason.** Escaped path IDs preserve identity but are poor labels. The observed trace already has
the source location needed for a readable display.

**Rejected.** Changing IDs or guessing how to reverse an escape encoding.

**Checks.** `tests/test_cli_story.py`, `tests/test_studio.py`.
