# AD-113 Requires names a component at its own level

A misspelled `requires.component` used to cover no dependency and still pass (#179).
Reject it as invalid contract input, even when no import uses it and no `complete_requires`
rule is declared. This is reference validity, not an undecidable architecture rule.

Resolve the target against the declaring contract's component labels only. An ancestor or
another mount cannot supply it. Apply the same parser check to root, recursive and historical
contracts; preserve the mounted pointer and target name in diagnostics. Invalid input must
not write a baseline or rewrite a graph.

Component labels must also be unique within that contract. Two different IDs with the same
label otherwise let one `requires` entry permit both owners. Reject the second label with
its pointer. Reusing a label in another contract level or mount remains valid.

No new rule, configuration or schema version. A valid declaration still permits a dependency;
it does not prove that the code uses it.

Evidence: `tests/test_requires_target_references.py` and the executable contract-validation demo.

Under the architect's evidence-backed budget authorization, unresolved calls move 523 → 530.
`validate --against 1c8e0e8` identifies exactly seven added call sites: six Path operations in
the nested-input preflight and the new exception's `super().__init__`. These are additional
source operations, not improved detection in unchanged code. The resolver is unchanged.
UNKNOWN remains 41, with 0 violations and 0 cycle edges; no violation exemption is added.
