# AD-54 A typed violation row is the one supported way to read a report's violations, and `ir.baseline` derives it once for everything that groups them

`ir.baseline.ViolationRow` carries `fingerprint`, source/target modules,
`symbol`, source/target components and `evidence_ids`. Missing kind-specific values
are `None`. Rules and subjects live only on the fingerprint.
`violation_rows(observation)` derives one row per violation; baseline counts and
rule/pair counts reuse it instead of maintaining separate record walks.

Originally `ir.codec.load_observation(path)` composed canonical decoding and parsing.
Untrusted report bytes required `parse_record` to reject empty violation `rule_ids`
at the boundary, enforcing the schema's `minItems: 1` before count derivation indexes
the first rule. No fallback should hide malformed records.

Issue #12 exposed consumers using internal columnar codecs. At this stage a new
API package and another violation JSON shape were rejected as duplicate surfaces.
Internal `public` remained driven by cross-component imports: the new consumer-only
names were not added. Their introduction dropped `ir.baseline` usage below half,
so the draft and self-contract replaced its module entry with `KnownViolation`,
`compare_violations` and `observed_violations`.

[AD-64](ad-64-archkeelapi-is-the-declared-external-contract-and-ir.md) later rejected the
I/O rationale: an existing `ir/digest.py` leak did not justify another. It moved
reads to the declared `archkeel.api` facade and removed codec I/O. This read path
and its original interface argument are historical.

Checks: `tests/test_violations.py` covers canonical loading, typed import and
construct rows, fingerprint agreement, the documented snippet and empty-rule
rejection. Decision/baseline tests, self draft/public parity and self validation
covered the shared derivation and corrected entries.
