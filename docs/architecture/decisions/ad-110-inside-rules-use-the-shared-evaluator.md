# AD-110 Inside rules use the shared evaluator

Evaluate inside rules with root evaluators over the same scan, scoped to parent
packages. Global targets supply evidence, not extra rule sources. Preserve mounted IDs.

Missing contracts and unsupported rules remain incomplete. Known violations survive,
but validation cannot write outputs. Green import edges need receipts for every
shown site, without relevant UNKNOWN or violation; excluded `TYPE_CHECKING` sites
are unchecked. Folder navigation declares no policy.

[Evaluator proof](../../../tests/test_inside_rule_parity.py);
[recursive loading](ad-111-recursive-inside-contract-tree.md).
