# AD-187 Class field assignments retain their sites

Record unannotated Python class assignments as static UML attributes, preserving
visibility, evidence and distinct assignment sites. Infer no type from initializers.
Writes to another object's attribute are not writer-class declarations.

This cannot complete member inventory; instance writes and dynamic creation remain
unproved. Public API field inventory still includes annotated fields only,
so UML assignments cannot enlarge it. The shared renderer consumes recorded
modifiers without new inference.

[Field proof](../../../tests/test_static_fields.py).
