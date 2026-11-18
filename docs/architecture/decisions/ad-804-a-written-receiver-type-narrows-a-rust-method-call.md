# AD-804: A written receiver type narrows a Rust method call

Status: accepted. Part of #880 and #1571. It extends AD-383 and AD-524.

## Context
#1571 gives a pair gap per call that may reach an inherent member in the file of its type (1,278 on
`native/`, AD-418). Rust writes each parameter, field and return type: many receivers are proven.

## Decision
The scan reads each receiver as a chain (`scan_chains.rs`); `impl_types.rs` follows the written
types along it.
- **Roots.** `self` of an exact block (AD-383); a parameter, a typed local or closure parameter
  with a proof (AD-524) and its type arguments (`scan_written.rs`); an untyped local (the chain of
  its initializer; in a nested block or shadowed, it holds up to the next `let` of its name); a literal; a call `f(..)`, `m::f(..)`, `T::f(..)`, a struct literal and
  a variant, when no name and no macro call of the `fn` can hide the path.
- **Steps.** A named field of an exact struct or a tuple struct field (AD-833); a method call with
  the written return type of the one member that it reaches (AD-383); `?` on `Result` and
  `Option`; `&`, `&mut`.
- **Patterns** (`scan_bodies.rs`). A name in `Some(..)`, `Ok(..)` and tuple patterns of `if let`,
  `while let`, a match arm, a let-else, a tuple `let` or parameter, a closure or a `for`: the part of
  the matched value; through a reference, the default binding mode binds `&T`. `mut` or `ref`
  inside a pattern, `@`, an alternative and a `Some`/`Ok` that the file can rebind give no type.
- **Std types.** The prelude or one unconditional `use` leaf of `std`, `core` or `alloc` binds the
  path, and no item, glob or module-level macro of the file can give the name. `impl_ty.rs` holds
  inherent std methods and the `Iterator` methods of the adapters, with return type and `self` form.
- **Lookup steps.** Rust tries the receiver by value, `&`, `&mut`, then the deref target, and at
  each step an inherent before a trait method. A method of the table counts for certain at the
  first step only: the receiver has its `self` form and it is of the receiver's own type (or a
  by-value `Iterator` method: a second one is E0034). An autoref or a deref target (`[T]` of
  `Vec<T>`, `str` of `String`, `Path` of `PathBuf`) counts only in a closed file (`impl_scope.rs`:
  each `use` starts at `std`/`core`/`alloc` or in the workspace and names no re-export of another
  crate, each glob is of `std`, no `extern crate`, only silent std macros) and when no trait of the
  prelude or the workspace has the name. No trait of `std` has a name of the table for its types.
- **Closures and loops (fixed set).** On `[T]`, `VecDeque<T>`, sets, `Option<T>` and maps: `iter()`
  gives `&T` (`(&K, &V)` for a map), `iter_mut()` `&mut T`, `into_iter()` `T` from a value and `&T`
  or `&mut T` through a reference; `keys`, `values`; `filter`, `take_while`, `skip_while` keep the
  item. The closure parameter of `map`, `filter`, `filter_map`, `find`, `any`, `all`, `for_each`,
  `flat_map`, `take_while`, `skip_while`, `position`, `max_by_key`, `min_by_key` has the item
  (`&Item` for a predicate; `find`, `any`, `all`, `position` take `&mut self`: closed file only).
  `for` calls `IntoIterator::into_iter(e)` by path. A name of a body holds only at its receiver
  sites there, where nothing else binds it.

At the call, `&`, `&mut`, `Box`, `Rc` and `Arc` are peeled one level at a time:
- A std type reaches no inherent member of the workspace (E0116); only the gaps of a member that a
  macro may define stay (#1196). So does an outside type: a type of a dependency that the manifest
  takes from a registry or git (such a crate cannot depend on the workspace), with no own or
  unknown type argument (it may deref to it). Its trait methods stay #1515 and #1516.
- An exact own type without a `Deref` impl reaches only its own blocks and the unplaced blocks of
  its crate. Its one member is the edge when the receiver is the type or one reference to it and
  AD-383 holds. A `&mut` field read through a shared reference is no edge.
- Any other receiver keeps every gap.

## Soundness
A written type is a proof; nothing is inferred. A type parameter, `impl Trait`, `dyn Trait`, an
`async fn`, a qualified path and a type alias are unknown. A chain through a binding of a `fn` with
a macro that is no `macro_rules!` of the workspace has no type (AD-524), nor has a chain in a gated
module. An autoref keeps the gap of AD-383; `Box`, `Rc`, `Arc` give no edge. `map` gives an unknown
item; an adapter outside the set, a non-std iterator and an array by value give no type.

## Price
`native/` self-check: 64 PASS, 28 UNKNOWN, unchanged; pair gaps 1,278 to 1,047 (steps 1 to 3;
the closed-file rule costs 2). New edges make more modules reachable, so the prune of #1571 keeps
some sound gaps. tokio 1.48.0: the same verdicts and gaps as main (gated, macro-written modules).
The edges show 24 real module pairs that the contract did not declare (e.g. `model.graph()
.imports()` from `archkeel_model.direction`); each is a call of a public member, follows the layer
order and meets no forbidden dependency, and the contract states it as a `requires`.

Tests: `impl_types_tests.rs`, `impl_types_outside_tests.rs`, `impl_types_pattern_tests.rs`, `impl_types_let_tests.rs`,
`scan_chains_tests.rs`; the rustc plants of `tests/test_collector_false_pass_rust_own_file_method.py`.
