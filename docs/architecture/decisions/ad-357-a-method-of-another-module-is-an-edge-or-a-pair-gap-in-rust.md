# AD-356 A method of another module is an edge or a pair gap in Rust

**Status.** Accepted. It amends AD-335 (the 5b-2c module edges) for issue #953 and epic #880.

**Decision.**
1. An inherent `impl` block at any depth is read with the path of its type and its members. A
   block that is not in the file of its type is foreign.
2. A path `c::S::m` names its member. When the file of `S` defines no `m` for `S`, each module
   with a foreign block of `S` that defines `m` is an `import` edge of the path (FP-29, path form).
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
   `no_component_cycles`; and the edge closes no cycle that a cycle rule reads (module level: `b`
   reaches `a`; component level: `b` reaches the component of `a`). A contract with inside
   contracts keeps every gap. No protocol change: protocol 9 carries both fields.
6. FP-31: a rule on a module pair reads direct imports. "`a` must not use `b`" means "`a` must not
   import `b` directly". `a -> c -> b` through a `pub use` in `c` is two edges, and a cycle or a
   layer rule reads both. This replaces the sentence "a rule on `a -> b` does not see it" of the
   5b-2c amendment of AD-335.

**Problem.** `impl crate::c::S { pub fn m() }` in `b` with `crate::c::S::m()` in `a`, and
`use b::T;` in the root with `use super::*; 5u8.m();` in `a`, gave PASS for "a must not use b",
and cargo fails in `a` without `b` (E0599).

**Rejected.** (a) A gap for each foreign `impl` block: the child modules of `scan` and of the
TypeScript collector make every run UNKNOWN. (b) An edge for each method call that matches a name:
a FAIL that may be false. (c) Drop a pair gap for one component without the cycle test: the hidden
edge can close a module cycle, and `no_component_cycles` would PASS. (d) Read the type of `x`: the
scan reads no types.

**Limit.** The scan reads no types, so a pair gap may be a name collision of the same arity. A
member that a macro generates, a trait `impl` in another module than its trait and its type, and a
trait of a crate outside the workspace that a glob brings in are not read (`docs/known-limits.md`).

**Tests.** `native/rust/src/impl_edges_tests.rs`, `tests/test_collector_false_pass_rust_impls.py`.

**Cost.** uv `crates/uv` (3e2f08f8e756, `exclude_test_sources`): 22 gaps before and after. native/
(`make self-validate-native`): 0 gaps before; 28 pair gaps kept after this change; after the
cleanup of the Rust collector (`rs-flow` requires `rs-edges`, the real use that #953 names) 23 stay:
module cycles of a type file and the files of its `impl` blocks (`scan`, the TypeScript collector,
`archkeel_facts.request`) and same-arity name collisions in the TypeScript collector.
