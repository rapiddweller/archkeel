# AD-25 Peers are isolated by one rule, not by n·(n-1) prohibitions

Use one sibling-isolation rule to forbid peer collector imports while permitting shared foundation
dependencies. Do not enumerate every ordered pair. The repository check must also detect a collector
omitted from the scope, so adding a sibling cannot silently bypass isolation.

Proof: [test_self.py](../../../tests/test_self.py).
