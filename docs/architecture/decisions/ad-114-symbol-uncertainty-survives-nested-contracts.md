# AD-114 Symbol uncertainty survives nested contracts

Evaluate symbol limits at every contract level within its valid source modules.
A complete Dart directive scan cannot prove imported names; nesting must retain
that uncertainty and mounted evidence. Invalid children cannot import foreign facts.

Undecidable imports remain UNKNOWN; forbidden names remain violations. Both can
coexist with overall FAIL. Whole-module publication and explicitly allowed names
remain decidable. Scan completeness stays separate from symbol resolution.

[Coverage proof](../../../tests/test_inside_rule_coverage.py).
