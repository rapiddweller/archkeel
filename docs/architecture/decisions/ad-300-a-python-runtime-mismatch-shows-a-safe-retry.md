# AD-300: A Python runtime mismatch shows a safe retry

**Status.** Accepted. Issue #836.

**Decision.**
1. A Python runtime mismatch names the running version and the full declared project range.
2. Its remedy gives a `uvx --python <compatible-version> archkeel <command>` template. The user
   selects a version that satisfies the full range.
3. Studio shows the diagnostic subject, uncertainty and remedy when explore fails.
4. A mismatch keeps the failed result incomplete. ArchKeel does not install or switch Python.

**Reason.** A lower bound alone can select a version outside the full range. The user needs the
current version, the complete requirement and a safe retry command.

**Rejected.** Automatic installation or runtime selection; choosing the range's lower bound.

**Limits.** A command template cannot prove that a selected Python is available. The user must
select a supported version that satisfies the project's range.

**Checks.** `tests/test_runtime.py`, `tests/test_studio.py`, and the `validation-runtime-mismatch`
demo variant.
