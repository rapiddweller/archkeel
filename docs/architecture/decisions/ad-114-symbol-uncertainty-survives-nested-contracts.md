# AD-114 Symbol uncertainty survives nested contracts

Historical scope: the Dart statement below predates Analyzer-backed UML. See [AD-211](ad-211-dart-source-facts-use-the-official-analyzer.md)
for current statically resolved facts; unresolved imports and runtime behavior remain UNKNOWN.

Evaluate symbol limits at every contract level within its valid source modules.
A complete Dart directive scan cannot prove imported names; nesting must retain
that uncertainty and mounted evidence. Invalid children cannot import foreign facts.

Undecidable imports remain UNKNOWN; forbidden names remain violations. Both can
coexist with overall FAIL. Whole-module publication and explicitly allowed names
remain decidable. Scan completeness stays separate from symbol resolution.

[Coverage proof](../../../tests/test_inside_rule_coverage.py).
