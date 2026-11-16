# AD-590: Every Rust public item is documented, and a helper lives with its owner

Status: accepted (owner decision). Part of #880.

## Context
All Rust modules had a `//!` line, but nothing kept it so. Public items had no `///` in many
places. `docs/architecture/target/design.md` still described the deleted Python core (`Check`,
`Analyzer`, `render`); the native contracts, `native.md` and `shell.md` now state the target.

## Decision
1. Each non-test `.rs` file under `native/` starts with a `//!` line that names its
   responsibility. `tests/test_native_conventions.py` checks it.
2. `missing_docs` is `deny` in `[workspace.lints.rust]`. A public item has a short `///` that says
   what it is or what it means, not how it works. `pub(crate)` items are out of scope.
   `archkeel-facts`, `archkeel-contract` and `archkeel-report` carry `#![allow(missing_docs)]` with
   a stated reason in `lib.rs`: their fields and variants (the schema keys and the report columns)
   are not documented yet, and some come from macros. Items outside macros there have docs.
   Remove the allow when the last one is documented; the test lists the crates that may carry it.
3. There is no central utils module. A helper lives in the component that owns its meaning. Code
   that several crates share lives in the lowest crate that owns that meaning (`pytext`,
   `snapshot`, `facts`, `build-support`). A helper that one crate uses stays in that crate. No
   module, file, directory or crate is named `util`, `utils`, `common`, `helper`, `helpers`,
   `misc` or `shared` (Rust under `native/`; Python under `src/` and `tests/`).
4. `docs/architecture/target/design.md` is deleted. Git history keeps it.

## Consequences
A new public item without a doc, a new module without a `//!` line and a module with a junk-drawer
name each fail the build or `tests/test_native_conventions.py`.
