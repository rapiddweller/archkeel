# AD-76 `boundary_types` and `symbol_placement` are restrictions in `--against`

`validate --against` classifies `boundary_types` and `symbol_placement` like the other
restriction rules. Adding either rule narrows the contract and passes. Removing either rule
drops a restriction and fails as a widening unless an amendment covers the exact change.

The rule-kind partition is checked against `ArchitectureRule`'s reflected `RULE_KINDS` set.
The classifier still fails closed for a runtime kind it does not know: an unclassified kind is a
widening, never neutral.

Reason: both rules constrain the code's public shape. Treating them as unknown made an ordinary
contract hardening look like a widening and left the result dependent on a missing list entry.

Rejected: a second hand-maintained list in the test or contract schema. The typed rule union is
the source of truth; the widening module owns only the permission/restriction partition.

Check: `tests/test_widening.py::test_rule_kind_widening_table`,
`tests/test_widening.py::test_every_typed_rule_kind_has_one_widening_classification` and the
`--against` rows in `fixtures/demo_catalog_widening.py`.
