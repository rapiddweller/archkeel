# AD-804: A written receiver type narrows a Rust method call

Status: accepted. Part of #880 and #1571. It extends AD-383 and AD-524.

## Context
#1571 gives a pair gap for each method call that may reach an inherent member in the file of its
type: 1,278 gaps on `native/`, each one holding the rules that it can change (AD-418). Rust writes
the type of each parameter, field and return value, so many receivers have a proven type.

## Decision
The scan reads each receiver as a chain (`scan_chains.rs`); `impl_types.rs` follows the written
types along it.
- **Roots.** `self` of an exact block (AD-383); a parameter, a typed local or a typed closure
  parameter with a proof (AD-524), with its type arguments (`scan_written.rs`); an untyped top-level
  local, as the chain of its initializer; a literal; a call `f(..)`, `m::f(..)`, `T::f(..)`, a struct
  literal and a variant, when no name and no macro call of the `fn` can hide the path.
- **Steps.** A named field of an exact struct; a method call with the written return type of the
  one member that it reaches (the rule of AD-383); `?` on `Result` and `Option`; `&` and `&mut`.
- **Std types.** A path names a std type when the prelude or one unconditional `use` leaf of `std`,
  `core` or `alloc` binds it and no item, glob or module-level macro of the file can give the name.
  `impl_ty.rs` holds inherent std methods and the `Iterator` methods of the adapters, with the return
  type and the `self` form of their std signature.
- **Lookup steps.** Rust tries the receiver by value, then `&`, `&mut`, then the deref target, and
  at each step an inherent method before a trait method. A method of the table counts for certain
  at the first step only: the receiver has its `self` form and it is of the receiver's own type (or
  a by-value `Iterator` method: a second trait method of the name is E0034). An autoref or a deref
  target (`[T]` of `Vec<T>`, `str` of `String`, `Path` of `PathBuf`) counts only in a closed file
  and when no trait of the prelude or of the workspace has the name.
- **Closed file** (`impl_scope.rs`). A trait is called only when it is in scope. Each `use` leaf
  starts at `std`, `core`, `alloc` or in the workspace; a workspace leaf names nothing that the
  workspace re-exports from another crate, and no module re-exports a glob of another crate; each
  glob is of `std`; no `extern crate` and no macro call other than a silent std macro. No trait of
  `std` has a method of a name of the table for these types.
- **Closures and loops (fixed set).** On `[T]`, `VecDeque<T>`, sets, `Option<T>` and the `keys` and
  `values` of maps: `iter()` gives `&T`, `iter_mut()` gives `&mut T`, `into_iter()` gives `T` from a
  value and `&T` or `&mut T` through a reference; `filter`, `take_while`, `skip_while` keep the item.
  The one untyped parameter of the closure argument of `map`, `filter`, `filter_map`, `find`, `any`,
  `all`, `for_each`, `flat_map`, `take_while`, `skip_while`, `position`, `max_by_key` or `min_by_key`
  has the item (`&Item` for a predicate). `find`, `any`, `all`, `position` take `&mut self`: closed
  file only. `for x in e` calls `IntoIterator::into_iter(e)` by path, with no lookup. The binding
  holds only at the receiver sites of its body, where nothing else binds the name.

At the call, `&`, `&mut`, `Box`, `Rc` and `Arc` are peeled one level at a time:
- A std type reaches no inherent member of the workspace (E0116); only the gaps of a member that a
  macro may define stay (#1196).
- An exact own type without a `Deref` impl reaches only its own blocks and the unplaced blocks of
  its crate. Its one member is the edge when the receiver is the type or one reference to it and
  AD-383 holds. A `&mut` field read through a shared reference is no edge.
- Any other receiver keeps every gap.

## Soundness
A written type is a proof; nothing is inferred. A type parameter, `impl Trait`, `dyn Trait`, a
tuple, an `async fn`, a qualified path and a type alias are unknown. A chain through a binding of a
`fn` with a macro that is no `macro_rules!` of the workspace has no type (AD-524), nor has a chain in
a gated module. An autoref keeps the gap of AD-383, and `Box`, `Rc`, `Arc` give no edge. `map`
gives an unknown item; an adapter outside the set, a non-std iterator and an array by value (its
item depends on the edition) give no type.

## Price
`native/` self-check: 64 PASS, 28 UNKNOWN, unchanged; pair gaps 1,278 to 1,098 (the closed-file
rule costs 2). New edges make more modules reachable, so the prune of #1571 keeps 46 sound gaps.
tokio 1.48.0: verdicts and 63,834 gaps unchanged (gated and macro-written modules, paths `T::new`).
The edges show 22 real module pairs that the contract did not declare (e.g. `model.graph()
.imports()` from `archkeel_model.direction`). Each is a call of a public member, follows the layer
order and meets no forbidden dependency; the contract states them as `requires`, and
`docs/architecture/native.md` draws the four new component edges.

## Tests
`impl_types_tests.rs`, `scan_chains_tests.rs` and `scan_written.rs`; the plants of
`tests/test_collector_false_pass_rust_own_file_method.py` compare with the target that rustc prints.
