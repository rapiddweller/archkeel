# AD-502 A registry or git dependency is no edge to a crate of the workspace

**Status.** Accepted. Part of #880, issue #946. It narrows the amendment of 2026-11-10 in AD-335.

**Problem.** AD-335 says that each dependency a manifest declares is a crate edge. The collector
matched the package name against the crates of the workspace. A crate that depends on
`base-crate = "1"` (a registry version) or `{ git = … }` got an edge to a workspace crate of the
same name, although Cargo fetches that name from elsewhere. `REQUIRES` gave a false FAIL.

**Decision.**
1. A dependency is an edge to a crate of the workspace only when its entry has a `path`, or it has
   `workspace = true` and the entry in `[workspace.dependencies]` has a `path`.
2. Any other entry (a version only, `git`) is an external package. The import record is an external
   target, also when a crate of the workspace has the same name.
3. `workspace = true` with an entry that is a registry version follows point 2. `workspace = true`
   with no entry of that name in `[workspace.dependencies]` has no known source: the edge stays as
   before and the crate is UNKNOWN with a named gap.
4. A package that one manifest names with a path entry and with a registry entry (for example a
   dev-dependency) is local.
5. A manifest, or its workspace root, with a `[patch]` or `[replace]` table keeps the old rule,
   because such a table can point a registry name at a path.
6. A UTF-8 byte order mark at the start of a manifest is not part of its text, as for Cargo.

**Reason.** A false FAIL asks the owner to declare a dependency that does not exist. Point 3 and 5
keep the edge where the source is unknown, so no edge goes missing silently.

**Limits.** The transitive crate closure of impl blocks still follows each dependency by package
name; it can add a pair gap, never remove one.

**Tests.** `tests/test_collector_false_pass_rust_layout.py` (registry, git, workspace, patch,
missing entry, byte order mark); `native/rust/src/manifest_tests.rs`, `resolve_tests.rs`,
`toml_tests.rs`.
