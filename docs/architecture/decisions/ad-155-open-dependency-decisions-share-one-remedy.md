# AD-155 Open dependency decisions share one remedy

Emit one root `decision.open` diagnostic with the count. Keep ordered pair facts
and optional suggestions in `open_decisions`, avoiding a panel per pair.
The remedy uses explicit component `requires` and `complete_requires` policy,
including exact-module owners.

Observed imports cannot grant permission. Terminal panels prefer diagnostic codes;
exit policy and verdicts remain unchanged.

[Onboarding proof](../../../tests/test_onboarding_demo.py).
