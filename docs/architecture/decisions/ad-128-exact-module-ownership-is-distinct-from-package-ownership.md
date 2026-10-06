# AD-128 Exact module ownership stays distinct from recursive packages

Keep recursive `packages` ownership distinct from `exact_modules`, which owns
only listed identities. Combine selectors without precedence; multiple matching
components mean ambiguity. Missing exact modules cannot be satisfied by descendants.

Exact parents contain only the same exact child; recursive parents may contain either.
Target keeps absent exact leaves without inventing files. Whole-package endpoint
rules can decide component pairs, including exact members; partial endpoints cannot.
Exact-only pairs need explicit closed-world policy to close otherwise open decisions.

Absent and empty selectors preserve legacy digests. Null, malformed and duplicate
names are invalid. Exact references participate in widening and rename checks.

[Ownership proof](../../../tests/test_exact_module_ownership.py).
