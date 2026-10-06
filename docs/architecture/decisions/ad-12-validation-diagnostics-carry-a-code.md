# AD-12 Validation diagnostics carry a code

Every `contract_invalid` diagnostic carries a stable `DiagnosticCode`, such as
`decision.open`, `interface.unused` or `rule.violated`. The constructor requires
it; result JSON emits it beside the pointer. Pre-validation analyzer diagnostics,
such as `rule_without_subjects`, retain their kind without a code. Remove codes
that no path can produce.

Sixteen findings had shared one kind, forcing tests and agents to match prose.
Check: the constructor and the [AD-11](ad-11-every-checkable-item-has-a-catalogued-demo.md)
catalog compare codes instead.
