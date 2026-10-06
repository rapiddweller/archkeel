# AD-120: Direct publication crosses only declared ancestors

A real outside consumer can prove local use of a directly published child API,
without a wrapper. Every crossed ancestor boundary must publish the route;
stop at the caller's common ancestor.

Reuse facade membership and unique ownership. Private boundaries block evidence;
publication alone is not use. This affects lifecycle and planned-entry diagnostics,
grants no permission and removes no violation.

[Direct-publication proof](../../../tests/test_inside_direct_parent_publication.py).
