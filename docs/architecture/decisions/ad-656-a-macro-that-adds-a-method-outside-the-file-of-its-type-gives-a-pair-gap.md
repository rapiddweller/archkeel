# AD-656 A macro that adds a method outside the file of its type gives a pair gap

**Status.** Accepted (owner order: fix the false PASS). Part of #880, closes #1196. It amends AD-357 and AD-383.

**Reason.** A method call `s.m()` whose receiver the scan does not prove gets a pair gap to each module whose `impl` block outside the file of its type defines `m` (AD-357). An `impl` block that a `macro_rules!` call writes is not read, so it gave no gap: `a -> d` was PASS while rustc calls the `m` that `mk!(m)` adds in `d` (#1196). A `fn $name` was not even read as a member, because a metavariable stands after `fn`.

**Decision.**
1. A `macro_rules!` body is read at item level (`macro_items.rs`): the types that it defines (`struct`, `enum`, `union`, by name or metavariable), the trait and the self type of each `impl` (one identifier or one metavariable; a path is no name), and `fn $name`.
2. An `impl` of the expansion is anchored when the expansion defines its self type, or when the module of the call declares its trait or its self type by that one name (a struct, an enum or a trait at module level). This is the file rule of AD-357 and the anchor of AD-516 for a macro. A call of another macro, a path call and a macro definition in the body hold an expansion that the reading does not see: such a body is not anchored.
3. A member of an expansion that is not anchored gives a pair gap from each method call of its name that the scan does not prove, to the module of the macro call. Its visibility is not read.
4. A `macro_rules!` body makes no new identifier, so a `fn $name` takes one of the identifiers of the call tokens. Each of them is a member name of the module of the call. A body that is anchored adds such a name only to its own type, which no written type of a receiver proof is, so it holds back no proof.

**Why it is sound.** A method of a block in the file of its type, or anchored by its trait, is reached only by a value of that type or a use of that trait, which the scan treats as for a written block. Each other block that an expansion can write gets the gap of a written foreign block. A name that the expansion can give the method is in the call tokens.

**Measured.** Self-check on main: 86 PASS before and after. The first form (every macro member as foreign) gave 3863 pair gaps and 24 UNKNOWN rules; with the anchor of items 2 and 4 the self-check keeps 0 gaps.

**Rejected.** Every macro member as foreign: `as_str` of each closed enum gave 2392 pair gaps, while those blocks are in the file of their type. A path as an anchor: `impl crate::c::S` in `d` names another file (#1196).

**Tests.** `tests/test_collector_false_pass_rust_macro_method.py` (rustc accepts each plant; three of the five give a false PASS without item 3), `tests/test_collector_false_pass_rust_receiver_forms.py` (the two forms of #1215), `impl_receivers_cfg_tests.rs`.
