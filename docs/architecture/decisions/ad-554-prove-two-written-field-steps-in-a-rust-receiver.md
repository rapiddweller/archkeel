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
