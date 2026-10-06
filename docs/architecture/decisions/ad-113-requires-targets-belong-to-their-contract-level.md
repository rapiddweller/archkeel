# AD-113 Requires names a component at its own level

Resolve `requires.component` against unique labels in its declaring contract.
A misspelling previously permitted nothing and still passed. Other mounts or
ancestors cannot supply targets; labels may repeat across levels.

Reject invalid references without imports or `complete_requires`. Apply the parser
check to recursive and historical contracts, preserving mounted pointers.
Invalid input cannot write outputs. Valid permission does not prove use.

[Reference proof](../../../tests/test_requires_target_references.py).
