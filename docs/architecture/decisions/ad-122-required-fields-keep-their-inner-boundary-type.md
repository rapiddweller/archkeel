# AD-122 Required field wrappers keep their inner boundary type

`boundary_types` checks `Required[T]` and `NotRequired[T]` as `T` when the wrapper is
unambiguously imported from `typing` or `typing_extensions`. This lets a typed `TypedDict`
field be checked without mistaking optional presence for an unknown type.

A local lookalike, ambiguous binding, or malformed argument stays UNKNOWN. A broad inner type
still violates the rule. This changes analysis only, not the Python type or runtime value.

Check: `tests/test_boundary_types_aliases.py` and the CE finance facade report.
