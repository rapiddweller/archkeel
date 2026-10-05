# AD-95 A boundary type allowance names one nested field finding

`boundary_types.allowed_positions` is an exact exception for an owned DTO field that crosses a
declared facade. Its four coordinates are the facade function's `qualified_name`, signature
`position`, relative `field_path`, and field `annotation`. It does not exempt a function or
source. The outer signature annotation remains on the violation; an exact match removes only
that nested finding and emits a `FACT` in `typing_signals` with the rule and function evidence.
An unmatched allowance changes nothing and emits no fact.

AD-188 preserves the complete leaf declaration beside each member finding. Nullable and proven
Optional spellings match their own collected text, without semantic normalization. One outer map
may be selected; other findings and UNKNOWN survive. Ambiguous declarations and multiple outer
maps remain unallowed. Member-only permissions cannot pin a nullable field or union alias.

AD-123 later permits `field_path: ""` for an exact top-level parameter or
return finding. It matches the complete signature annotation and exempts one
top-level broad finding, including one inside an optional union. Nested maps,
undeclared members, and UNKNOWN evidence remain visible. If there are multiple
top-level broad findings, the root allowance matches none. A root allowance cannot name a
bare `Dict`, `Mapping` or `MutableMapping`: the parser and schema reject it.
AD-135 permits an exact `object` / `object | None` payload as accepted opacity, with explicit provenance;
it does not prove type closure. Other bare mapping spellings never match a root allowance.

The contract parser rejects malformed and duplicate entries. Adding an allowance widens the
contract and `--against` requires an amendment; removing one narrows it. A bare `dict` remains a
violation when the allowance names `dict[str, JsonValue]`.

Check: `tests/test_boundary_types_nested_dtos.py`, `tests/test_contract_model.py`,
`tests/test_widening.py`, `make self-observation`, and the self ratchet.
