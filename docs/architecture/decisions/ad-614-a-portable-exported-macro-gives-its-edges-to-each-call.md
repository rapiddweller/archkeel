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

## An unlisted name with a proven route fails
A use of a name that a module defines twice under `cfg` (`plant::skip` of the TypeScript collector)
was UNKNOWN: the route needed one declaration of the name, so it stopped after the first hop, and an
unlisted name with no public hop kept the gap "unproven publication route". When no `use` leaf, glob
or `extern crate` of the module binds the name, only a definition of the module gives it, whatever
the number of declarations, so the route ends there (`routes::defined_here`). The use of an unlisted
name then fails. A route that the scan does not prove (a macro may write `pub use`) stays UNKNOWN.
A route of a type (AD-608) still needs one written type.

## The scan of the test sources has no gap left
With the test sources (the oracle `test_the_scan_of_native_is_complete`), the scan named 55 gaps.
- 44: a name that an inline module (`mod tests`) imports again counted twice in its file. A name
  of a child module is no name of its parent, so the one declaration is read in the inline module
  of the path (`scoped_counts`); the alias check keeps the count of the file.
- 9: a glob of a module with macro calls in item place may bring in a name that a macro defines.
  A call whose expansion writes no `use`, `extern` or `mod` at item level defines no module of the
  name (`filled::binds_nothing`, the proof of item 5 of AD-608).
- 2: the word `core` in a string. A string of code, or of a `std` macro, is a value: it stays in the
  net only when it is path-shaped (`name::rest`). A string of `json!` (a macro of another crate)
  stays a gap, so the test data of `html_views_tests.rs` names its component `domain`.

## Tests
`tests/test_cli_native_rust_macro_crate.py` (rustc accepts each plant):
- a portable call by path and through a `use` gives the edge of the expansion, which fails the
  interface rule for an unlisted name and passes for a listed one;
- a body with a bare `crate` path keeps the gap (UNKNOWN);
- `tests/test_cli_native_rust_interface.py`: a name with two definitions under `cfg` fails when it
  is unlisted and passes when it is listed; a name that a macro may publish further stays UNKNOWN.
