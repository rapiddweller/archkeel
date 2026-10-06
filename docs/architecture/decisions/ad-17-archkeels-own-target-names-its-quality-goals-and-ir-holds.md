# AD-17 Archkeel's own target names its quality goals, and `ir` holds pure derivations

Keep deterministic evaluation over typed IR, isolated collection, replaceable rendering and a thin
CLI. Evidence derivations perform no I/O and import no outer layer. This gives one result that each
host can render without repeating architecture policy.

Checker-source identity is a separate boundary exception:
[AD-64](ad-64-archkeelapi-is-the-declared-external-contract-and-ir.md). Proof:
[test_self.py](../../../tests/test_self.py).
