# AD-293 Python detection checks `src` before the repository root

**Status.** Accepted. Issue #827.

**Decision.** Use `src/` when it contains a top-level Python package. If it has no such package,
search the repository root. Keep the existing package-name match when several packages exist.
When detection fails, name the directories searched in the scope diagnostic.

**Reason.** Repositories can use `src/` for another language and keep Python at the root. An
existing `src/` directory alone does not prove that Python uses it.

**Rejected.** Always prefer `src/`; require `--source` for a root package. The first misses valid
Python layouts. The second makes a deterministic layout needlessly manual.

**Limit.** Detection recognizes packages by `__init__.py`, as before. Namespace packages and
other layouts still need explicit `--source` and `--namespace`.

**Checks.** `tests/test_onboarding.py` checks root fallback, package-name selection, and retained
`src/` selection. `tests/test_explore.py` checks the Rust-only `src/` demo and the reported scope.
