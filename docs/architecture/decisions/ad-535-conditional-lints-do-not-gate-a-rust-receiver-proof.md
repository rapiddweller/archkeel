# AD-535 Conditional lints do not gate a Rust receiver proof

**Status.** Proposed. Part of #880. This amends AD-383 and AD-524.

The receiver proof needs each item and its module in every configuration. A `cfg` can remove
an item. An attribute macro can rewrite one. Both keep the gap.

**Decision.** A `cfg_attr` is inert for this proof only when it parses, has a condition and at
least one payload, and every payload is a plain `allow(...)`, `warn(...)`, `deny(...)`,
`forbid(...)` or `expect(...)` lint. A conditional lint cannot remove or rewrite the item.
The rule applies to the caller, its body, its enclosing modules, its type, its impl and its member.
The other receiver checks stay in force. A `cfg`, nested `cfg_attr`, unknown attribute, malformed
input, qualified attribute or mixed lint and non-lint payload still prevents this proof.

The module import scanner has a separate test for attributes. It reads possible module edges.
Its looser name test is not sufficient to prove an exact receiver.

**Alternatives.** Treating every `cfg_attr` as a gate holds real edges. Accepting all attributes
that look inert would need a proof for each one. Reading the active Cargo features would not
prove the other configurations. None of these is the chosen rule.

**Measurement.** On main `7ea82d8fe`, native self-check gaps fall from 113 to 107. The rule
statuses remain 63 PASS, 0 FAIL and 20 UNKNOWN. There are no violations. The other `Source` calls
still have other refusals, including an unproved `matches!` call. No fact type is changed.

**Tests.** The conditional lint plant fails before the change and proves the forbidden edge after.
The non-lint plants keep the gap for `cfg`, nested and mixed payloads, malformed arguments and
qualified names. Five mutations test parsing, a missing payload, every payload, the lint name and
the lint list form. `impl_receivers_tests.rs` and `test_collector_false_pass_rust_param_receiver.py`
hold the plants.
