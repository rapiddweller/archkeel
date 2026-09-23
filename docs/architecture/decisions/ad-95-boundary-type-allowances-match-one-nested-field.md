# AD-95 A boundary type allowance names one nested field finding

`boundary_types.allowed_positions` is an exact exception for an owned DTO field that crosses a
declared facade. Its four coordinates are the facade function's `qualified_name`, signature
`position`, relative `field_path`, and field `annotation`. It does not exempt a function or
source. The outer signature annotation remains on the violation; an exact match removes only
that nested finding and emits a `FACT` in `typing_signals` with the rule and function evidence.
An unmatched allowance changes nothing and emits no fact.

The contract parser rejects malformed and duplicate entries. Adding an allowance widens the
contract and `--against` requires an amendment; removing one narrows it. A bare `dict` remains a
violation when the allowance names `dict[str, JsonValue]`.

Check: `tests/test_boundary_types_nested_dtos.py`, `tests/test_contract_model.py`,
`tests/test_widening.py`, `make self-observation`, and the self ratchet.
