# Python receiver origins

Issue: #542. Base: 6fba15000baaeff6a274058291654b7301f2077a.
Branch: fix/542-python-receiver-origin.

## Approved bounded design

The existing receiver_types module owns ReceiverOrigin with LITERAL, ANNOTATION and
DOCUMENTED values. ReceiverType stays in that module, retains its constructor shape,
and normalizes valid legacy strings once in its frozen post-init. The Origin import
name remains an alias of the nominal type. Invalid values raise ValueError.

Calls produces and merges nominal origins; resolve keys its existing verdict table
by ReceiverOrigin. Type names, method tables and wire status/reason text stay data.
No additional UNKNOWN origin, namespace inference or method-resolution authority.
Ambiguous and shadowed receiver bindings retain their existing unresolved outcomes.

## Steps

- [x] Commit this plan before production changes.
- [x] RED: nominal field/producer identity, real calls._bind_receiver raw dispatch,
  invalid legacy inputs, and actual Source versus an independently authored origin Target.
  Pin valid legacy verdicts, merge order and ambiguous/shadowed controls at the same time.
- [ ] Replace the origin Literal with the owned Enum, retain Origin as an alias,
  normalize ReceiverType inputs once with builtin-qualified object.__setattr__,
  and migrate calls/resolve without changing their algorithms.
- [ ] Keep one whole-module guard only for the completely migrated receiver_types
  module; verify raw equality/membership/Enum.value source mutations and
  origin-to-str widening against unchanged Targets.
- [ ] Run receiver/call/lexical/source/binding regressions, Ruff, Mypy and native
  validation against this exact base with 918 unresolved / 58 unknown / 52 typing / 0
  violations. Generate/replay the normal v2 amendment without changing budgets.
- [ ] Deliver an isolated PR and freeze the exact product source for final Astra.

## Isolation

Property operation/origin and its legacy Dict/wire port remain a separate increment.
The Source physical-line correction in #553 remains independent and must be preserved
when the branches are combined. Temporary verification workflows stay outside product.

RED evidence: hosted run38955338212, candidate d0bba4984dd1ad9f3218ab3e02827a2e8f0d3fae:11 expected assertion/validation failures, no setup errors. Actual Source fails the authored origin Target and native observations expose the raw literal-merge comparison.
