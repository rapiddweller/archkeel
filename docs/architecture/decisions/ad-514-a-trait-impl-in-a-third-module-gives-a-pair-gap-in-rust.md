# AD-514 A trait impl in a third module gives a pair gap in Rust

**Status.** Proposed. Part of #880. Closes the main class of #1004 and its row in #1075. It
extends AD-357.

**Problem.** An impl of a trait for a type runs wherever the types fit; no `use` names it. One
crate: `b.rs` holds `impl From<crate::a::Y> for crate::c::S`, `a.rs` calls `y.into()`, a rule says
`a` must not use `b`. Deleting `mod b;` fails `a` (E0277), yet the verdict was PASS with no gap.
The same holds for `S::from`, `?`, operators, `Deref`, `Display`, `for`, `Default`, `==`, `Drop`,
`AsRef`, `TryFrom`, `Index`, a blanket impl over closures, generic dispatch, and `x.m()` of a
local trait for a local type in a third module. The scan reads no types.

**Rule (written before the code).**
1. The *head* of a trait impl is the trait path, the self type and every path in the generic
   arguments of both. A type parameter of the impl is no path.
2. A head path is *defined* in module `b` when it resolves to a struct, enum, union or trait of
   the file of `b`, or is one name that a block around the impl declares as one of these.
3. An unresolved path (alias, glob name, macro type, foreign path) is not defined. Strict is
   allowed, weak is not.
4. An impl with no defined head path is an orphan of `b`. Each module that may reach it gets the
   pair gap `m -> b`, written as in AD-357; the host drops it when the contract allows the pair
   and no cycle closes (AD-418). A pair that an edge joins gets no gap.
5. May reach: each module of the crate of `b` and of each crate that depends on it.

**Proof of the bound.** Coherence gives an impl no scope: code of crate `K` runs an impl of crate
`X` only when `K` is `X` or `X` is in the Cargo closure of `K`. Any module of that set can hold a
value of the type without naming it (a function returns it, `Default::default()` infers it). The
scan has no type of a value, so no smaller set is provable.

**Anchored impls keep their verdict.** An impl in the module of its type, of its trait, or of a
type argument is not an orphan. A caller can reach it only through a value of a type of that
module: the class "a method on a value of a type the caller does not name" (AD-418).

**Open false PASS, not accepted (a pinned plant each).** A value of a type of `b` that `a` gets
from `c`, with `impl From<Y> for String` in `b`. An impl that a macro of `b` generates (#1020). A
trait of a crate outside the workspace that a glob brings in (AD-357).

**Price (measured).** `make self-validate`: native 63/1/19 and 124 pinned gaps, shell 22/0/0; the
pins do not move. `native/` had one orphan, not none: `impl From<Cause> for Reason` in
`receipts.rs`; it moved to `reason.rs`. Five impls are anchored by the block or argument rule;
without those two anchors the rule flagged six modules and moved the pins. The fixture matrix
has 22 runs, none in Rust. General: an orphan in a crate of `N` modules gives `N - 1` gaps plus
the modules of dependent crates. A contract that lets every module use `b` pays nothing;
otherwise the cure is to move the impl to the module of its type or trait.

**Where.** `native/rust/src/orphan_impls.rs` (the rule, below `impl_edges.rs`); `scan_definitions.rs`
(`trait_impl`, `block_type`); `impl_globs.rs` (`once_gap`, `depends`). No model, core or report
source names a language.

**Mutations (each run).**

| Change | Fails |
|---|---|
| No gap (the code before) | 19 use plants, cross-crate, forbidding contract |
| Callers: crate of `b` only | the cross-crate plant |
| Head without argument paths | the argument control; the open form turns into a gap |
| Block declarations ignored | the control for a block type |
| Unresolved path counts as defined | the alias and glob plants |

**Plants (28).** 21 fail first on `0a9a20576` (PASS there): 19 use forms, the crate that depends
on the crate of `b`, and the forbidding contract. After: UNKNOWN. The allowing contract, 4
controls and 2 open forms give PASS before and after. `tests/test_collector_false_pass_rust_orphan_impl.py`;
`native/rust/src/transitive_edges_tests.rs` pins `impl Trait` and `Box<dyn Trait>`.
