# AD-357 A method of another module is an edge or a pair gap in Rust

**Status.** Accepted. It amends AD-335 (the 5b-2c module edges) for issue #953 and epic #880.

**Decision.**
1. An inherent `impl` block at any depth is read with the path of its type and its members. A
   block that is not in the file of its type is foreign.
2. A path `c::S::m` names its member when `c` defines the struct, enum, union or trait `S` (also
   through a renamed `use`). When the file of `S` defines no `m` for `S`, each module with a foreign
   block of `S` that defines `m` is an `import` edge (FP-29, path form). A path call that the scan
   cannot resolve exactly (`<T>::m`, a type alias, a re-export, a glob-imported type, or a type
   that a foreign block of an unknown type may extend) is a call as in 3, of any arity.
3. A method call `x.m(..)`, in code or in a macro body, can reach a foreign member `m` that has a
   `self` parameter, as many other parameters as the call has arguments (Rust has no overloads),
   and a visibility that holds the caller: private reaches nothing, `pub(super)` the parent of the
   block and below, `pub(crate)` and `pub(in ..)` the crate, `pub` also the crates that depend on
   it. A path `T::m` into another crate of the workspace can reach any foreign member `m`. Each
   such member in module `b` gives the caller `a` one gap of the pair, unless `a` already has an
   edge to `b` (FP-29, method form). The gap has `source_module` `a` and `module` `b`.
4. A glob of `a` that brings in the names of module `X` (also through the globs of `X`) brings in
   each `use` leaf of `X`. A leaf that names a trait of module `b`, or a name whose kind the scan
   does not know, gives the same pair gap when `a` calls a method of that trait (any method for an
   unknown kind) and has no edge to `b` (FP-30). A glob chain longer than eight is a gap of `a`.
5. The host drops a pair gap only when the contract lets `a` use `b`: one component, or a
   `requires` without `through`; no `forbidden_dependency`, `allowed_dependency` or
   `sibling_isolation` names `a` or `b`; no rule of a kind outside the edge-free kinds and
   `no_component_cycles`; and, for each active cycle level, `a` and `b` (or their components) are
   in two cycle groups of the graph of the known edges plus every pair gap. So two gaps `a -> b`
   and `b -> a`, a chain of gaps, or a known edge from another module of the component of `b`
   keep the gap. A contract with inside contracts keeps every gap. Protocol 9 carries both fields.
6. FP-31: a rule on a module pair forbids a direct use; a use through a re-export is seen by the
   layer and cycle rules. `a -> c -> b` through a `pub use` in `c` is two edges, and a module cycle
   through it is FAIL. This replaces "a rule on `a -> b` does not see it" of the 5b-2c amendment of
   AD-335.

**Problem.** `impl crate::c::S { pub fn m() }` in `b` with `crate::c::S::m()` in `a`, and
`use b::T;` in the root with `use super::*; 5u8.m();` in `a`, gave PASS for "a must not use b",
and cargo fails in `a` without `b` (E0599).

**Rejected.** (a) A gap for each foreign `impl` block: the child modules of `scan` and of the
TypeScript collector make every run UNKNOWN. (b) An edge for each method call that matches a name:
a FAIL that may be false. (c) Drop a pair gap for one component without the cycle test: the hidden
edge can close a module cycle, and `no_component_cycles` would PASS. (d) Read the type of `x`: the
scan reads no types.

**Limit.** The scan reads no types, so a pair gap may be a name collision of the same arity. Open
false PASS, not accepted: a trait `impl` in another module than its trait and its type, and a trait
of a crate outside the workspace that a glob brings in (#1004), and a member that a macro generates
(#1020).

**Tests.** `native/rust/src/impl_edges_tests.rs`, `tests/test_collector_false_pass_rust_impls.py`.

**Cost.** uv `crates/uv` (3e2f08f8e756, `exclude_test_sources`): 22 gaps before and after.
native/ (`make self-validate-native`): 0 gaps before, 33 kept pair gaps after (pairs that the
contract forbids, or that together with the edges and the other gaps may close a cycle), and
`rs-flow` now requires `rs-edges` (the use that #953 names). The first native PASS of native/ is
withdrawn: part of it came from method calls into `impl` blocks of other files that the scan did
not see. The cycles of a type file and its `impl` files are real under the current rule. A gap
makes every rule UNKNOWN, so the gate pins the exact 33 gaps and the status of each rule
(`native/expected-gaps.json`, `tools/native_expected.py`): a new or a missing gap, another status or
a violation fails it. A parent/child option of the cycle rule is a later, separate decision.

**Amendment (2026-11-12, AD-383).** Point 3 has one exception: a call on a plain `self` in a method
of `impl S` is an edge to the module of the inherent member `m` of `S` and gives no gap, when that
member has the same `self` form and the block and the member are exact
([AD-383](ad-383-a-method-call-on-a-plain-self-is-an-exact-edge-in-rust.md)). The pin of
`native/expected-gaps.json` also lists each known violation with its follow-up issue.
