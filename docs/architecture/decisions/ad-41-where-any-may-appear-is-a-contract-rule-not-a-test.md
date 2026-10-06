# AD-41 Where `Any` may appear is a contract rule, not a test

Keep `Any` permissions in the architecture contract with scoped owner rationale. Do not duplicate
them in a source regex: test and report policy could drift. At a JSON boundary, `object` is an
honest type and remains a typing-ratchet signal; it is not an `Any` annotation.

Proof: [test_source_types.py](../../../tests/test_source_types.py) and
[test_self.py](../../../tests/test_self.py).
