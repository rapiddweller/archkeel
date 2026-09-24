# AD-102: A constant JSON cannot hold is recorded without its value

A module-level constant becomes a `static_constant` symbol. Its literal goes into `data.constant`
only when JSON can hold it: `str`, `int`, `bool`, `None` or a finite `float`. A `bytes`, `complex`,
`Ellipsis` or non-finite `float` constant keeps its symbol record but no `constant` field.

## Why

The observation is JSON. `CACHEDIR_TAG_CONTENT = b"Signature: ..."` in pytest's
`_pytest/cacheprovider.py` made the bundled analyzer stop with `TypeError: Object of type bytes is
not JSON serializable`, so `init`, `report` and `validate` exited 2 for the whole package.

## Rejected

- **A string form such as `repr(value)`.** `boundary_types` accepts a `str` constant as a
  `Literal` member, so `b"x"` stored as `"b'x'"` would prove a member the code does not have.
- **Dropping the symbol.** The name is still a module binding that imports and facades resolve.

## Limit

A constant without its value proves no `Literal` member: `Literal[TAG]` over such a constant stays
UNKNOWN (`reason: other`), never PASS. The check requires the `constant` key, because a missing
value would otherwise read as the `None` literal.

## Check

`tests/test_boundary_type_literals_aliases.py::test_a_constant_json_cannot_hold_is_observed_without_its_value`
covers `bytes`, `complex`, `...` and `1e999`, keeps a `str` constant's value, and pins
`Literal[TAG]` as UNKNOWN.
