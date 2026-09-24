# AD-102: A constant JSON cannot hold is recorded without its value

A module-level constant becomes a `static_constant` symbol. Its literal goes into `data.constant`
only when UTF-8 JSON can hold it, which the encoder itself decides: a `str`, `int`, `float`, `bool`
or `None` that `json.dumps(..., allow_nan=False)` writes and UTF-8 encodes. A `bytes`, `complex` or
`Ellipsis` constant, a `str` with a lone surrogate, an `int` beyond Python's digit limit and a
non-finite `float` keep their symbol record but no `constant` field.

## Why

The observation is JSON. `CACHEDIR_TAG_CONTENT = b"Signature: ..."` in pytest's
`_pytest/cacheprovider.py` made the bundled analyzer stop with `TypeError: Object of type bytes is
not JSON serializable`, so `init`, `report` and `validate` exited 2 for the whole package.
`Cs = '\ud800-...'` in `pygments/unistring.py` stopped `report` the same way when the observation
was written as UTF-8. A type list alone misses these values; the encoder does not.

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
covers `bytes`, `complex`, `...`, `1e999`, `"\ud800"` and a 3,600-hex-digit `int`, keeps a
`str` constant's value, and pins `Literal[TAG]` as UNKNOWN.
