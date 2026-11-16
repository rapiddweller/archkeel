# AD-614: A portable exported macro gives its edges to each call

Status: accepted (owner order). Part of #880. It amends AD-604. The lead may renumber it.

## Context
A `#[macro_export]` `macro_rules!` expands in each crate that calls it, so the Rust collector named
every exported macro a gap of its module ("is exported: it expands in other crates"). That gap held
rules. The four `env!` values of `provenance()` were therefore copied in the Rust and the TypeScript
collector (a clone of 75 tokens), as one shared macro would have been a gap.

## Decision
1. `$crate` names the crate that defines the macro, wherever the macro expands. A bare `crate`
   names the crate of the call. A body is portable when each `crate` of it is `$crate`
   (`tokens::only_dollar_crate`), each path of it starts with `$crate`, it names no `self` or
   `super`, the scan reads all of it, and it calls only itself, a silent macro of `std` or a `std`
   expression macro (`env`, `concat`, `stringify`, ...).
2. A portable exported macro is no gap. The scan keeps the edges of its `$crate` paths (as for a
   `crate` path of a local macro), and a call in another crate takes them. The call names the macro
   by its path `dep::m!`, or by its plain name through the one `use` leaf of the file that binds it.
   A `#[macro_export]` macro is an item of the root of its crate.
3. Any other exported macro keeps the gap.
4. `facts` exports `native_provenance!`. The Rust and the TypeScript collector call it, so the clone
   is gone and `tests/test_rust_clones.py` passes.

## Tests
`tests/test_cli_native_rust_macro_crate.py` (rustc accepts each plant):
- a portable call by path and through a `use` gives the edge of the expansion, which fails the
  interface rule for an unlisted name and passes for a listed one;
- a body with a bare `crate` path keeps the gap (UNKNOWN).
