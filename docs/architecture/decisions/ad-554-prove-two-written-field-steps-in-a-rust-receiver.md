# AD-554 Prove two written field steps in a Rust receiver

**Status.** Proposed. Part of #880. This extends AD-543.

The receiver proof can follow two named field steps. Each step needs the exact visible field and
written plain type of AD-543. A third field, an alias, a generic type, a `Deref` impl, a changed
field, or an unresolved type keeps the gap. A shared base or intermediate reference cannot prove
a unique field. A typed closure parameter can give the base at a recorded call site.

**Proof.** Each visible field of an exact struct has the written type in every configuration.
The next field is read in that type's module, not guessed from its spelling at the call. Shared
access cannot provide a unique reference behind it. After the second step, the first-step method
rule of AD-383 applies without a dereference assumption.

**Measurement.** On #1214 the self-check stays at 96 gaps. The current Dart chains also need
conditional-module, alias and const-generic proofs. No violations are exempted.

**Tests.** `test_two_written_field_types_prove_a_receiver` fails before the rule. The field
plants cover a third step, typed closure base, changed fields, aliases, generic types and `Deref`.
Five mutations check the depth limit, closure site and shared-borrow checks.

**Macro review.** A workspace macro can pass an attribute macro through its tokens. The scan
keeps the receiver gap when those tokens contain `#[...]`. A derive attribute also keeps the gap:
a custom derive can emit an import that hides the receiver. A macro can also introduce a type
name in a function body. A typed local or closure with an unqualified type therefore keeps the
gap when the function calls a macro that is not a silent standard macro. A path rooted at
`crate`, `self` or `super` keeps its proof. These checks fix the two receiver findings of the
review of AD-543. The reviewer plants and two mutations check the refusals and the controls.

**`matches!` amendment.** The standard macro expands to a `match`. Its pattern bindings are
inside the match arm and guard, not the enclosing function. A receiver call outside the macro
can use its written type even when its name occurs in the tokens. A call inside those tokens
keeps the gap. A workspace macro or import that can shadow `matches!` also keeps the gap.
This amends AD-535. The self-check removes two TypeScript pairs, with no violations.

**Gated modules.** A direct `self` receiver can be proved across file modules whose written
`cfg` chains are identical in the same crate. The caller, type and member are then present
together. Different chains, opaque attributes, gated typed parameters and field projections
keep the gap. The scan does not infer equivalence between different conditions. The earlier
experiment exposed module cycles; no cycle is exempted and main must measure the result.

**Derive helpers.** A type with `serde` or `schemars` container attributes can be exact when
the existing registry and namespace proof establishes that each is a helper of a known derive.
Other attributes and unproved helpers keep the gap. Derives add items without rewriting the
type; rustc rejects a generated inherent method duplicating the written one (E0592). Field
projection still needs its separate field-attribute proof. The preliminary identity index does
not use these new exact types to prove itself.
