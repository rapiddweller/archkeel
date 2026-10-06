# AD-115 Nested API lifecycle uses local evidence

Evaluate nested API lifecycle using evidence from that mounted level.
Cross-sibling imports and proven ancestor facades inside the parent count as use;
unrelated publication cannot. [AD-120](ad-120-direct-publication-crosses-only-declared-ancestors.md)
also permits direct outside consumers through every crossed boundary.

Reuse scoped facade and unique-binding evidence. Missing binding metadata supplies
no proof; Dart imports do not acquire Python publication semantics.
Missing modules remain `interface.missing`, unused public entries `interface.unused`.
Unused planned entries stay target work; observed use requests promotion without
granting access. Unknown imported names cannot prove non-use.

[Lifecycle proof](../../../tests/test_inside_publication.py).
