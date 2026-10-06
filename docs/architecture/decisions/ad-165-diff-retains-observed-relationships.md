# AD-165 Diff retains observed relationships

Draw Core's recorded unlisted relationships in Diff with endpoints, kinds, sites,
evidence and assessments. Typed entity correspondences reuse Core matching; they
add no verdict or copied entity contents. Older comparison payloads remain readable.

Fold endpoints by ID. Ambiguous matches stay separate observed cards; missing
endpoints create no hit areas. Grouping retains every site and source graph.
An unlisted call does not make its callee an unlisted definition.

[Diff proof](../../../tests/test_uml_rendering.py).
