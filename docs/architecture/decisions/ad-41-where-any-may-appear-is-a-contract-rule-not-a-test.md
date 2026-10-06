# AD-41 Where `Any` may appear is a contract rule, not a test

The self-contract's `CONSTRUCT-NO-ANY` forbids `any_annotation`, allowing only
open-JSON owners `archkeel.ir.codec` and `archkeel.analyzer.embedded`
([AD-2](ad-02-json-has-one-type.md)). Remove `tests/test_source_types.py`'s duplicate
regex and path exemptions. The analyzer already observes annotations and
`forbidden_construct` evaluates `allowed_sources`, so no new code is needed.

Keeping both would let test and report decisions drift. `object` remains a ratchet
signal; at a JSON boundary it is an honest type, not an `Any` annotation.
Check: the self-rule recorded zero violations; moving `dict[str, Any]` outside
those owners produced `rule.violated` in `report`.
