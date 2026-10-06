# AD-122 Required field wrappers keep their inner boundary type

Check `Required[T]` and `NotRequired[T]` as `T` only when the wrapper is
unambiguously imported from `typing` or `typing_extensions`. Optional field presence
does not make the field's type unknown.

Lookalikes, ambiguous bindings and malformed arguments remain UNKNOWN.
A broad inner type still violates `boundary_types`. This changes analysis only,
not Python types or runtime values.

[Wrapper proof](../../../tests/test_boundary_types_aliases.py).
