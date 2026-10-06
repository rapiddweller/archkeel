# AD-44 An undeclared added dependency edge is a guardrail failure, closing the AD-39 Limit

Reject undeclared new edges, while allowing explicitly selected edge additions and ordinary
removals. Do not reject growth merely because a total rises. Other guardrails reject new regressions
independently; improvements elsewhere cannot offset them.

This keeps change intent specific without turning the selection into blanket approval. Proof:
[test_expectation.py](../../../tests/test_expectation.py).
