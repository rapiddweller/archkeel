# AD-92 Undecided declared evidence is UNKNOWN by default and measured

Count undecided positions centrally, defaulting new unknown kinds to a positive count. Exclude
duplicate coverage failures, standing call/context/private-access disclaimers and external boundary
types; retain finer profile counts where supplied. Otherwise use positive `undecided` or one.

This scalar supports ratchets and baseline budgets. Legacy payloads read zero.
[AD-124](ad-124-rule-pass-requires-complete-scope-receipt.md) replaces the original aggregate PASS
derivation. Proof: [test_unknown_positions.py](../../../tests/test_unknown_positions.py).
