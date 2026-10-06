# AD-117 Report verdicts require evaluator evidence

Render rule verdicts from evaluator receipts, violations and UNKNOWN evidence.
An empty finding list does not prove that a rule ran; missing receipts cannot yield PASS.
Permissions remain declarations. Known violations stay FAIL alongside undecided positions.

An explicit read-only baseline classifies debt without changing the verdict.
Resolution requires complete current evaluation of old subjects, including cycle members;
narrowed scope cannot resolve omitted debt. Mixed fingerprints retain counts without
assigning old debt to individual occurrences. Resolved means absent under current
rules, not proven repair; use `validate --against` for policy widening.

[Receipt proof](../../../tests/test_inside_rule_coverage.py) and
[baseline proof](../../../tests/test_baseline.py).
