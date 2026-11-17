# AD-786: A written receiver type narrows a Rust method call

Status: accepted. Part of #880 and #1571. It extends AD-383 and AD-524.

## Context
#1571 gives a pair gap for each method call that may reach an inherent member in the file of its
type. On `native/` that is 1,270 gaps, and each gap holds the rules that it can change (AD-418). Rust
writes the type of each parameter, field and return value. A large part of these calls has a
receiver whose type follows from these written types alone.

## Decision
The scan reads the receiver of each method call as a chain (`scan_chains.rs`): a root and the steps
after it. The resolver (`impl_types.rs`, `impl_ty.rs`) follows the written types along the chain.

- **Roots.** The `self` of a method of an exact block (AD-383). A parameter, a typed local or a typed
  closure parameter with a proof (AD-524), with its written type and type arguments
  (`scan_written.rs`). An untyped top-level local, as the chain of its initializer. A literal. A
  call `f(..)`, `m::f(..)` or `T::f(..)`, a struct literal `T { .. }` and a variant `T::V`, when no
  name of the `fn` and no macro call of the `fn` can hide the path.
- **Steps.** A named field of an exact struct, with its declared type. A method call with the
  written return type of the one member that it reaches (the rule of AD-383: exact type, one exact
  member, the same `self` form, the same arity, certainly visible). `?` on `Result` and `Option`.
  `&` and `&mut`.
- **Std types.** A path names a std type only when the prelude or one unconditional `use` leaf of
  `std`, `core` or `alloc` in its scope binds it, and no item, glob or module-level macro of the
  file can give the name. A fixed table holds inherent std methods with the return type of their
  std signature. A method of a deref target (`[T]` of `Vec<T>`, `str` of `String`, `Path` of
  `PathBuf`) counts only when no trait of the prelude and no trait of the workspace has the name.
- **Closures and loops (fixed set).** On `Vec<T>`, `[T]`, `&[T]`, `VecDeque<T>`, sets, `Option<T>`
  and the `keys` and `values` of maps: `iter()` gives `&T`, `iter_mut()` gives `&mut T`, and
  `into_iter()` gives `T` from a value and `&T` or `&mut T` through a reference. `filter`,
  `take_while` and `skip_while` keep the item. The one untyped parameter of a closure that is the
  one argument of `map`, `filter`, `filter_map`, `find`, `any`, `all`, `for_each`, `flat_map`,
  `take_while`, `skip_while`, `position`, `max_by_key` or `min_by_key` has the item; the predicates
  (`filter`, `find`, `take_while`, `skip_while`, `max_by_key`, `min_by_key`) see `&Item`. The variable
  of `for x in e` has the item of `into_iter()` on `e`. Such a binding holds only at the receiver
  sites of its body, and only when the body binds the name nowhere else.

At the call, `&`, `&mut`, `Box`, `Rc` and `Arc` are peeled one level at a time:
- A std type reaches no inherent member of the workspace: an inherent impl of a std type is E0116.
  The call keeps only the gaps of a member that a macro call may define (#1196).
- An exact own type without a `Deref` impl reaches only its own members. Its blocks, and the
  unplaced blocks of its crate (an inherent impl is in the crate of its type), keep their gaps. Its
  one member gives the edge when the receiver is the type or one written reference to it and the
  rule of AD-383 holds.
- Any other receiver keeps every gap.

## Soundness
- A written type is a proof; no type is inferred. A type parameter of the `fn` or the block,
  `impl Trait`, `dyn Trait`, a tuple, an `async fn`, a qualified path and a type alias are
  `Unknown`.
- A chain through a binding of a `fn` with a macro that is no `macro_rules!` of the workspace, or in
  a workspace where a macro may stand for a silent std macro, has no type (AD-524). A gated module
  reads no chain.
- An autoref keeps the gap: a `&self` member reached through a value is no edge, because a
  by-value trait method in scope could win (AD-383). Through `Box`, `Rc` and `Arc` the call is never
  an edge.
- `map` gives an unknown item: the scan does not read the type of a closure result. An adapter
  outside the fixed set, a non-std iterator and an array by value (its `into_iter` item depends on
  the edition) give no type.

## Limit
The table and the deref rule do not read the traits of a crate outside the workspace and std. Such a
trait with a method of a name of the table, implemented for the std type and in scope, would win
the call at an earlier step. The table holds only names of inherent std methods that the traits of
the prelude do not use.

## Price
| project | rules | pair gaps |
|---|---|---|
| `native/` self-check | 64 PASS, 28 UNKNOWN to 64 PASS, 27 UNKNOWN, 1 FAIL | 1,270 to 1,097 |
| tokio 1.48.0 guard | unchanged | 63,834, unchanged |

`NATIVE-REQUIRES-COMPLETE` changes from UNKNOWN to FAIL: 66 edges between components of `native/`
that the contract does not declare, for example `model.graph().imports()` from
`archkeel_model.direction` into `archkeel_model.graph`. Each one is a real call of a member of the
module. tokio keeps its gaps: its modules are gated or written by macros, and most of its
method-call gaps are paths `T::new`.

## Tests
- `native/rust/src/impl_types_tests.rs`: std receivers, own types with and without an exact form,
  written return types, untyped locals, `Box`, a type with a `Deref` impl, the fixed adapters and
  loops, and the forms outside the set.
- `native/rust/src/scan_chains_tests.rs`, and the unit tests of `scan_written.rs`.
- `tests/test_collector_false_pass_rust_own_file_method.py`: rustc prints the real target. A written
  return type `&S`, a closure of `iter().map` and a loop over `&[S]` give the edge (FAIL);
  `String::from(..).len()` reaches std, and the rule keeps its PASS.
