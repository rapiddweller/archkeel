# AD-112 Public means public at that boundary

Each level declares its own public API. Equal parent/child lists forced sibling
APIs onto the outward surface. Outside callers still need parent publication or
a proven facade; children cannot override ancestor restrictions.

Validate local ownership, namespace, provenance and private names. Interface rules
also require scanned public modules. Old mismatch results remain readable but
are no longer emitted.

[Publication proof](../../../tests/test_inside_publication.py);
[local lifecycle checks](ad-115-nested-api-lifecycle-uses-local-evidence.md).
