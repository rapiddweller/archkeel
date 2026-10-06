# AD-30 A declared owner is worth nothing until something can contradict it

Repeated-logic claims find an exact AST-shape twin outside a declared `spot_owner` when another sits
inside it. Ignore names, literal values and docstrings, and shapes below ten nodes. Accept missed
near-matches rather than add floating-point similarity thresholds.

Matches are review candidates, not violations or permission to merge behavior. Proof:
[test_duplication.py](../../../tests/test_duplication.py).
