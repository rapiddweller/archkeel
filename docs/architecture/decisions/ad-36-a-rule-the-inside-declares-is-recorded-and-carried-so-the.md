# AD-36 A rule the inside declares is recorded and carried, so the verdict it produces survives every command

Qualify inner rule IDs with their parent and carry explicit parent identity. Do not reconstruct
hierarchy by splitting names. Snapshot mounted contracts for reproducible comparison, and retain
every violation's rule and evidence through serialization.

Recursive mounting and provenance follow [AD-110](ad-110-inside-rules-use-the-shared-evaluator.md)
and [AD-111](ad-111-recursive-inside-contract-tree.md). Proof:
[test_contract_model.py](../../../tests/test_contract_model.py).
