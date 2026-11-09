# AD-338 A validation run parses each reference excerpt once, and the dependency proof parses bound records only

**Decision.** Two host steps parse less. The output of `explore` does not change.

1. `validate_reference_contexts` (`ir/reference_contexts.py`) keeps a memo for one call. The key is
   (excerpt, column, expression). The value is a `SourceReferenceContext` or `None`, both
   immutable. The call creates the memo and drops it at its end.
2. `bound_sections` (`ir/dependency_binding_kinds.py`) hands only bound raw records to
   `parse_record`. It uses `binds_reference`, the test that `dependency_binding_id` also uses.
   Calls are bound only with `include_calls`.

**Reason.** In a profile of `explore` on a private Python repository, the reference-context check
parsed 164 055 excerpts in 4 validations. The dependency proof of an incomplete scan parsed every
call and unused reference, and then dropped them. The measurement is in issue #880.

**Rejected.**
- A module global or `functools.cache` for the memo. Studio and MCP keep one process for many
  projects, so a global cache grows without a bound and can mix two projects.
- One memo for the four validations of a run. It saves more, but a run owner must pass it through
  `evaluate_source` and the decode. This needs a decision about that contract.

**Limit.** One call has 32 811 checks for 26 472 distinct excerpts (1.24 times), so the memo gives
little. A malformed record of an unbound kind is not parsed in the proof. `parse_observation`
rejects it later in the same run and labels it `references[]` or `calls[]`, not `record`. A record
without a text kind is still rejected in the proof. The whole run is 6.5 % faster on a private
repository (macOS), below the 10 % bar of CONTRIBUTING. `bound_sections` is a new public name of
`ir`; `ad-338-parse-less-amendment.json` binds it.

**Check.**
- `test_source_reference_context_memo`: one parse for a repeated excerpt, a new parse in the next run,
  the key holds all three parts, the verdicts equal those without a memo.
- `test_dependency_binding_filter`: the proof id equals the id of the old definition, for four
  flag pairs and 40 seeds. Only bound records reach `parse_record`. Malformed bound records fail.
- `architecture.json` differs only in `analyzer.code_digest`. Both HTML pages are byte-identical.
