# AD-93 `boundary_types` follows owned declared DTO fields

`boundary_types` recursively checks the fields of an owned declared DTO, including types reached
through known collection and union members. It tracks origins on the active field path, so cycles
stop while the same DTO reached through sibling fields is checked once per path.

Nested violations and undecidable positions retain the signature's `annotation`. Their `path`
starts at the signature parameter or `return`, and `nested_annotation` names the field annotation
that produced the finding. Contract schema stays unchanged; the analyzer version rises to
`0.44.0` because observations change.

Unsupported shapes and unresolved or ambiguous names remain UNKNOWN. This extends AD-84's bounded
field read without adding runtime reflection or guessing at Python types.

Check: `tests/test_boundary_types_facades.py`, `make self-observation`, and the self ratchet.
