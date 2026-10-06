# AD-111 Explicit inside contracts form one revision-bound tree

Load every explicit `inside` mount through one revision-bound contract tree.
Folders never discover policy. Refuse missing, malformed, cyclic, duplicate or escaping
mounts; retain mount-qualified IDs and clipped ancestor source scopes.

Ancestor and sibling ownership can resolve targets, but adds no rule sources or automatic
publication. Ambiguous ownership remains UNKNOWN; known violations survive incomplete
branches. Incomplete validation cannot write outputs.

Checks authenticate the accepted tree; comparisons include deep policy changes.
Observations bind raw bytes, amendments bind canonical contracts. Legacy root-only
amendments cannot approve newly included child policy.

[Tree proof](../../../tests/test_recursive_inside_contracts.py) and
[boundary proof](../../../tests/test_recursive_contract_boundaries_astra.py).
