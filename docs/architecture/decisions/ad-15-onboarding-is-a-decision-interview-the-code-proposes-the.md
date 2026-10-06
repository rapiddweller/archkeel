# AD-15 Onboarding is a decision interview: the code proposes, the architect decides

`init` observes facts and drafts a decision interview. It does not authorize observed dependencies.
The architect supplies permissions or prohibitions and their reasons; source-backed agent
suggestions remain proposals until decided.

Keep open decisions derived from the same observation.
[AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md) replaces exhaustive
pair declarations with `requires`. Proof: [test_onboarding.py](../../../tests/test_onboarding.py).
