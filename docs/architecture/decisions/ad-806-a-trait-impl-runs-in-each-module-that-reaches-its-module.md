# AD-806 A trait impl runs in each module that reaches its module

**Status.** Accepted (lead order: #1515 and #1516). Part of #880, closes #1515 and #1516. It amends AD-516 (its open false PASS) and uses the value flow of #1571 (`impl_flow.rs`). The rule is in `orphan_impls.rs`, beside the gaps of AD-516.

**Reason.** `impl Tr for Y` in `b` runs where a value of `Y` meets a use of `Tr`. The caller writes no name of `b`:
- a method call on a value that another module gives (`c::make().m()`, a field, a closure argument, an alias with `Default`, `impl Tr`, `Box<dyn Tr>`);
- an implicit call: `Display` and `Debug` through `to_string` and the format macros, `Drop`, `==`, `+`, `[]`, `*` through `Deref`, `?` through `From`, `into()`, and `Iterator::next` in `for`;
- a trait of `b` reached through a generic bound `T: b::Tr` in another module, a supertrait, a `dyn` supertrait or a re-export, and a foreign trait that a glob brings in.

AD-516 gives a gap only for an impl that neither its type nor its trait anchors. The 17 forms of #1515 and #1516 and the glob form have an anchored impl, and `NO-A-TO-B` gave PASS for each. `cargo check` accepts each plant.

**Decision.**
1. A module `b` *runs code of a trait impl* when its file holds a written trait impl block with an item other than an associated type (a `fn`, a `const`, a macro call), or a derive other than `Copy`: a derive writes an impl in the module of its item.
2. Each module that may run such an impl gets the pending pair gap `a -> b`. That is each module of the crate of `b`, and of each crate that depends on it, other than `b` itself. The value flow of #1571 gives the gap only when `a` reaches `b` over the edges and the pair gaps of the reply, or reaches a module with a gap that names no target. It runs until no gap changes. A pair that an edge joins gets no gap; the host drops a gap that the contract allows (AD-357).
3. The candidate set does not depend on a method name or on a written operator. A drop, a generic call and a `dyn` call write neither, so no syntax can narrow it.

**Why it is sound.** A caller can hold a value of a type of `b` only from code that names that type. The same holds for a function whose bound or signature names a trait of `b`, and for a re-export or supertrait of that trait. That code is `b` or has a path to `b`, so the caller reaches `b` over the dependency graph. A module that does not reach `b` cannot run its impls. An impl block with only associated types runs no code of `b`. The code of a generic or `dyn` callee that runs an impl which its caller hands in is attributed to that caller, the module that reaches `b` and selects the impl. This is the inversion that the trait makes; the callee names only the trait.

**Price (measured on main `d2b873a94`).**
- Native self-check: 64 PASS, 28 UNKNOWN, 1090 gaps -> 62 PASS, 30 UNKNOWN, 21608 gaps; no FAIL, no violation.
  - `NATIVE-NO-CORE-TO-RUST` and `NATIVE-NO-CORE-TO-TYPESCRIPT` turn UNKNOWN: `core` reaches both collector crates through `collect`, and their modules hold trait impls and derives.
  - 20488 new gaps are trait-dispatch gaps. 30 are #1571 field-receiver gaps that the value flow now reaches over them.
  - On `aa280f686` the explicit impls alone gave 5045 new gaps; the derives give the rest.
- Frozen Serde: 4525 -> 4946 gaps, rows unchanged (0/1/3).
- tokio 1.48: 66155 -> 82672 gaps, rows unchanged (0/4/2), the same wall time.
- Three `target_symbol` plants of AD-668 go PASS -> UNKNOWN: the use of a type alias, a call of `make` alone, and the same beside an opaque root. They reach `base.vocab`, where the derived `PartialEq` of `Profile` runs.

**Not done here (follow-ups).**
- A receiver whose type is exact (the receiver-type facts of #1571 in progress, AD-383, AD-524, AD-543) with one exact trait impl of the method could be an edge to the module of that impl, which can turn an UNKNOWN into a FAIL. An edge does not remove the gap of rule 2, because the implicit forms remain.
- A crate whose published items carry none of its own types, no `dyn`, `impl Trait`, generic return or closure parameter, cannot hand a value of its types to another crate. With signature facts this could drop the cross-crate pairs, among them the two native rows above.

**Rejected.**
- Name candidates by the method name only, as the inherent members of #1571 do: a drop, an operator, a format, a generic or a `dyn` call has no name, and the false PASS stays.
- Leave derived impls out: a derived `PartialEq` of `Y` in `b` runs code of `b` as a written one does.
- Count the generic callee: the callee names the trait, not the type; with it, every module that a holder of the value reaches would get the gap.

**Tests.**
- `tests/test_collector_false_pass_rust_orphan_impl.py::test_a_dispatch_through_another_module_never_passes`: the 17 forms. It was `test_an_open_form_stays_a_named_false_pass`, which pinned PASS.
- `tests/test_collector_false_pass_rust_trait_dispatch.py`:
  - `Debug` through `format!`, `*` through `Deref`, `[]` through `Index`, and the glob of a foreign trait (from #1550) never pass;
  - a module that does not reach `b`, and an impl with only an associated type, keep PASS;
  - `cargo check` accepts each of the 23 plants.
- On main `aa280f686`, 21 of the 23 plants give PASS (false); the 2 controls pass.
