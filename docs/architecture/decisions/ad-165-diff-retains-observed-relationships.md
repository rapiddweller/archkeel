# AD-165 Diff retains observed relationships

Core already reports unlisted relationships in closed UML scopes. Diff must draw
those recorded sites, including their endpoints, kinds, evidence and assessments.

`GraphComparison` retains typed Target-to-observed entity correspondences from
Core's existing matching. Multiple matches remain explicit. Correspondences add
no verdict and copy no entity contents. The strict codec accepts old comparisons
without this optional field; the schema is generated from the dataclasses.

The renderer folds endpoints into visible Target cards by ID. Ambiguous counterparts remain
separate observed cards. Recorded parents determine scope; missing endpoints create no hit area.
Grouped edges retain every site and its source graph. Details reads Core's exact
receipts. An unlisted call does not make its callee an unlisted definition.

Explicit lexical scope endpoints use the normal card layout. They cannot overlap
the first child or reopen the same breadcrumb. Component interiors omit the owner
card and its parent-level permissions. Routing, arrows and focus use the shared boundary.
Adapter policy and observation format stay unchanged.

Proof: `tests/test_uml_comparison.py`, `tests/test_graph_comparison_codec.py`
and `tests/test_uml_rendering.py`. AD-166 adds observed-only interior navigation.
