# AD-124 A rule PASS requires a complete scope receipt

A rule PASS requires an evaluator receipt for a nonempty, completely scanned scope
with unique ownership. Empty or missing packages, partial containing scopes and
ambiguous or unowned modules cannot supply it. Physical paths and recorded module
identity both participate; unmappable domains cannot be omitted.

Only AST-empty Python initializers are exempt from ownership. Docstrings and imports
retain that obligation; no static imports does not prove absence of runtime effects.
Any undecidable non-declaration rule makes `declared_rules` UNKNOWN unless a known
violation proves FAIL.

[Coverage proof](../../../tests/test_inside_rule_coverage.py).
