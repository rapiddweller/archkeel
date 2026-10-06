# AD-102: A constant JSON cannot hold is recorded without its value

Module constants become `static_constant` symbols. Include `data.constant` only
when `json.dumps(..., allow_nan=False)` and UTF-8 encoding accept the literal.
Bytes, complex, Ellipsis, lone-surrogate strings, over-limit integers and
nonfinite floats retain symbols without values.

## Why

Pytest's bytes `CACHEDIR_TAG_CONTENT` caused a whole-package serialization failure;
Pygments' surrogate string caused UTF-8 output failure. A type allowlist misses
invalid values; the encoder checks the actual boundary.

## Rejected

`repr` would turn bytes into a false string Literal member. Dropping symbols would
lose real bindings used by imports and facades.

## Limit

A missing constant value cannot prove a Literal member; it remains UNKNOWN (`other`).
Require the key so absence cannot be mistaken for the None literal.

## Check

`test_a_constant_json_cannot_hold_is_observed_without_its_value` covers bytes,
complex, Ellipsis, infinity, surrogates and a 3,600-hex-digit integer, while retaining
valid strings and UNKNOWN for unsupported Literal values.
