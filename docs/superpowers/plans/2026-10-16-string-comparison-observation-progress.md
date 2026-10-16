# Issue #542 native comparison observation ledger

- Plan committed before tests on isolated fix/542-string-comparison-observation.
- Native RED run 38930770707: 14 failed, 11 passed; failures are missing named collection/bytes/enum value/main observations and existing shadowed-name false positives.
- Ruling: imported arbitrary runtime constants remain unclassified — cross-module global escape and runtime rebinding cannot be certified by this syntactic collector — a later independently reviewed binding-proof extension is required.
- Ruling: use existing LexicalScopes only to distinguish module bindings from parameters/locals — no compiler receipt or namespace-proof changes — dynamic bindings remain outside the guarantee.
- Ruling: named mutable literal collections must have visible membership-only loads — mutation and alias escape invalidate classification — this intentionally omits some valid literal vocabularies.
