# AD-153 Unproven chains retain declared signatures

When effective property-chain proof fails, retain evidenced declared
signatures alongside the aggregate UNKNOWN. Mark `signature_scope: declared`;
these candidates prove no active accessor, violation, exposed type or allowance.
Class creation may replace them.

Reuse owner and signature proof. Ambiguous or nested classes cannot borrow
evidence; proven final plain bindings suppress earlier chains. Counts describe
undecided declarations, not runtime accessors, and existing budgets can reject increases.
Reobserve changed checker identities before comparison.

[Candidate proof](../../../tests/test_owned_property_candidates.py).
