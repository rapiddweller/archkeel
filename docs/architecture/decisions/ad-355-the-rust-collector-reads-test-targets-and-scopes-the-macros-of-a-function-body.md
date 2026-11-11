# AD-355 The Rust collector reads test targets and scopes the macros of a function body

**Status.** Accepted. It refines AD-335 and AD-349 for issue #880.

**Decision.**
1. A test target is a root of its own module tree. The roots are `tests/*.rs`,
   `tests/<name>/main.rs`, the same two forms in `benches/`, `examples/` and `src/bin/`, and each
   `[[test]]`, `[[bench]]` and `[[example]]` of the manifest that names a `path`.
2. A test target has test scope. A request that excludes tests reads the root only for its
   `mod x;` declarations and leaves its modules out, with no gap. Without the flag, the
   modules and their edges are read as any other module.
3. A `macro_rules!` in a function body is visible from its definition to the end of that body.
   A call resolves to it only there. A macro with `#[macro_export]` stays crate-wide.
4. A call is UNKNOWN as "defined more than once" only when two definitions are visible at that call.
5. A leaf `use dep::{dep}` binds a name that also starts its own path. The path then starts at the
   crate, not at the leaf. This ends the "chain of use items is too long" gap of that form. A glob
   that may bring in the name stays UNKNOWN.

**Problem.** On `crates/uv` of uv, 85 of 111 files were "in no module tree", and `show_settings!`
(one definition in each of two functions) gave 51 gaps. The scan was incomplete.

**Rejected.** (a) Treat every file in `tests/` as a module of the library: it names a wrong module
and a wrong crate root. (b) Resolve a local macro by the file only: two functions of one file
still collide. (c) Lift the gap of a macro of another crate (`warn_user!`, `uv_snapshot!`): the
scan does not read its definition, so a path in its call stays UNKNOWN.

**Limit.** The scope is the text of the body, not a data-flow proof. A target that `autotests =
false` turns off is still read: this reads more, never less. A nested macro name with two visible
definitions is skipped as before.

**Tests.** `crates_tests.rs`, `collect_tests.rs`, `module_edges_tests.rs`, `modules_tests.rs`,
`tests/test_collector_false_pass_rust_test_targets.py`.

**uv, `crates/uv`, 3e2f08f8e756.** Without the flag: 26 of 111 files read before, 111 of 111 after;
the gaps rise from 166 to 1362 because the test targets are now read, and 1257 of them are the
`uv_snapshot!` macro of the crate `uv-test`. With `exclude_test_sources`: 166 gaps before (85 no
module tree, 51 `show_settings!`, 8 `warn_user!`, 5 use chains, 17 other), 22 after.
