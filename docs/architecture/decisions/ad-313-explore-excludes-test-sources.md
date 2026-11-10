# AD-313 Explore excludes recognized test sources

**Decision.** Default Python and TypeScript `explore` excludes files recognized by their test
naming and directory conventions. The collection request carries this scope in protocol 9;
protocols 1 through 8 keep their existing shape. Dart and other collection callers keep their
current behavior. Explicit governance scopes keep their current behavior.

An import from selected production source into an excluded test source is UNKNOWN. It is not a
complete observation of that import. Test names are classified by exact conventions; names such as
`latest.py` and `latest.ts` remain production candidates.

**Reason.** Implementation Explore should describe implementation code. Treating known tests as
implementation changes ownership and can hide the production structure.

**Limit.** Dart test exclusion is not implemented. The collector does not yet report counts and
reasons for intentionally excluded files. Unrecognized test naming remains in scope. This decision
does not close issue #874 until Explore and Studio expose the applied exclusions and their limits.
Programmatic Explore with a V1–V8 external collector fails at the V9 protocol boundary. CLI Explore
has no external collector override.

**Check.** Python and TypeScript source-root fixtures cover test exclusions, production named
`latest`, and production imports across the excluded boundary. The public demo catalog includes
`explore-excludes-test-sources`, with `shop/tests/test_latest.py` inside the selected root.
Protocol tests preserve V8 and round-trip the V9 scope. The issue remains open for exclusion
reporting and Studio coverage.

**Update 2026-11-10 (owner decision).** A new key `[scan] exclude_test_sources` (default false)
puts `report`, `validate` and `check` on the same test-free scope that `explore` uses. A project
opts in. The key has one meaning for every language. These facts hold:

- Explore keeps its behaviour. It sets the scope itself, for Python and TypeScript only, and it
  ignores the key.
- `TEST_SCOPE_LANGUAGES` (`ir/profiles.py`) is the one owner of the languages that honour the
  scope. Today these are Python and TypeScript. `ScanConfig` rejects the key for any other
  language, and the observer fails for it, so no language ignores the key silently. A Rust
  collector joins the set when it honours the scope.
- A file that the naming rule calls a test, such as `test_mode.py`, is excluded even when it is
  production code. This is the scope the project chose. It is never silent: the note names the
  count and the first 20 paths, sorted, and the human output prints the note.
- The host takes the list from the one listing of the files it hands to the collector. This is the
  worktree or the git tree of a revision. It keeps the list by git head and makes no second walk.
- `validate --against` adds a note when the key differs from the compared revision. A change of
  `scan.roots` has no such note today.
- `files_discovered` and `files_parsed` count the test-free scope. The result carries a
  `not_examined` note, so a PASS is not read as covering test sources.
- With the key absent or false, the request, the result and the bytes do not change.

**Reason for the update.** One repository must not get two scopes for one question. The report of
a project that owns its test code should describe production code only, as Explore does.

**Check for the update.** `tests/test_source_test_scope.py` runs `report` and `validate` with the
key on and off on a Python and a TypeScript fixture with a test file in the scan root.
