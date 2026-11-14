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
5. "No edge" holds only when the collector has read every place that can redirect the name and
   found none. The places: `[patch]` and `[replace]` in the manifest of the crate, in the workspace
   root above it and in the root that `package.workspace` names; `[patch]`, `[replace]`, `paths`
   and `[source]` in a `.cargo/config.toml` or `.cargo/config` of the crate directory and of each
   directory above it up to the scan root. A redirect in any of them keeps the old rule (a name of
   the workspace is an edge) for the whole crate. A place that cannot be read (a config that does
   not parse, a named root that is missing or outside the scan root) gives a named gap, and the
   old rule stays. The code is `native/rust/src/redirects.rs`.
6. A UTF-8 byte order mark at the start of a manifest is not part of its text, as for Cargo.

**Open false PASS, not accepted.** The collector does not read a config outside the repository
(`$CARGO_HOME/config.toml`, a config above the scan root), the environment (`CARGO_*`)
or the command line (`--config`). A `git` entry that points at the same
repository as a crate of the workspace is read as a registry name. In each case a redirect that
exists there turns a real edge into "no edge" and can give PASS. They are listed in
`docs/known-limits.md`.

**Second decision (#1021).** A pair gap `a -> b` that the drop rule drops because the contract
allows the pair is neither an observed edge nor an absent one. A component graph that draws
`a -> b` is held: `graph.drift` keeps its finding and its UNKNOWN, with its own text ("Drawn edge
a -> b can be neither confirmed nor refuted: the call in <module> may or may not reach b"). Only
the false text "drawn and not found" goes. A graph that does not draw the pair, and the target
graph, are unchanged. No verdict moves toward PASS by this point.

**Reason.** A false FAIL asks the owner to declare a dependency that does not exist. Points 3 and 5
keep the edge where the source is unknown, so no edge goes missing silently.

**Limits.** The transitive crate closure of impl blocks still follows each dependency by package
name; it can add a pair gap, never remove one.

**Tests.** `tests/test_collector_false_pass_rust_layout.py` (registry, git, workspace, each place
of point 5, unread places, byte order mark); `tests/test_collector_false_pass_rust_impls.py`
(held edge); `native/rust/src/manifest_tests.rs`, `redirects_tests.rs`, `resolve_tests.rs`,
`toml_tests.rs`; `native/core/src/hygiene_graph_tests.rs`.
