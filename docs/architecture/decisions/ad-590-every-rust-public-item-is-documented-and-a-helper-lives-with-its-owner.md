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
   Every crate takes the lint; none may carry `#![allow(missing_docs)]` (the test checks it). A
   macro that declares fields, variants or accessors takes the doc of each one from its input, so
   the doc stands next to the declaration. The JSON schema of `archkeel-facts` takes these docs as
   descriptions (a documented variant makes a `oneOf` of `const` words in place of an `enum`).
3. There is no central utils module. A helper lives in the component that owns its meaning. Code
   that several crates share lives in the lowest crate that owns that meaning (`pytext`,
   `snapshot`, `facts`, `build-support`). A helper that one crate uses stays in that crate. No
   module, file, directory or crate is named `util`, `utils`, `common`, `helper`, `helpers`,
   `misc` or `shared` (Rust under `native/`; Python under `src/` and `tests/`).
4. `docs/architecture/target/design.md` is deleted. Git history keeps it.

## Consequences
A new public item without a doc, a new module without a `//!` line and a module with a junk-drawer
name each fail the build or `tests/test_native_conventions.py`.
