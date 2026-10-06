# AD-105 A package rename is compared under its new names

Compare a proven package rename under its new names before checking widening.
Rewrite only declared module and symbol references, including baseline subjects and
roles. IDs, authorship and constructs keep their meaning; real widening still fails.

A substitution must preserve containment and scope, leave no old source or import
behind, and match physical layout. Python requires a complete historical scan using
the historical config. Unsupported layouts cannot authorize a rename; Dart changed-root
renames remain unsupported. A moved `inside` path still reports separately.

[Rename proof](../../../tests/test_renames.py) and
[physical-root limits](../../../tests/test_rename_physical_roots.py).
