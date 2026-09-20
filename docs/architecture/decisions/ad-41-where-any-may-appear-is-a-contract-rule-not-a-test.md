# AD-41 Where `Any` may appear is a contract rule, not a test

`CONSTRUCT-NO-ANY` forbids the
`any_annotation` construct across `archkeel` and exempts exactly the two owners [AD-2](ad-02-json-has-one-type.md) named, the
codec that decodes open JSON (`archkeel.ir.codec`) and the collectors that write it
(`archkeel.analyzer.embedded`); `tests/test_source_types.py` no longer greps the source for
`Any` with the same two exemptions hard-coded as path prefixes. Reason: the exemption list was
architecture knowledge held in a test, so `archkeel report` on this repository could pass while
the rule it did not know about failed in `pytest`, and a reader of the contract saw no decision
about `Any` at all; the analyzer already records every `Any` annotation as a typing signal and
`forbidden_construct` already evaluates that construct with `allowed_sources`, so the rule costs
no code. Rejected: keeping both, since two sources of one decision drift, and the regex
recognised three spellings while the analyzer recognises the annotation itself. Limit: the rule
matches `Any` in annotations, not the `object` escape hatch, which stays a ratchet signal ([AD-2](ad-02-json-has-one-type.md))
because `object` at a JSON boundary is the honest type, not an escape. Check: the rule passes on
the current source with zero violations, and moving one `dict[str, Any]` out of the two owners
is a `rule.violated` finding in `archkeel report`.

