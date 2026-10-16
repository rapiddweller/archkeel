# Preserve nominal values across legacy wire proof boundaries

**Scope:** Fix the observed scoped dependency proof and widening prose regressions on Graph+Version `5933ffbbfd588ac96e36748de937cb1f6e739655`; preserve the independent Diagnostics increment.

**Cause to prove:** Open JSON string values retain StrEnum object identity when frozen in memory, while JSON replay produces plain strings. The established dependency proof hashes the historical Record/Evidence representation; it must see the same canonical primitive values at issuance and replay. Existing widening field prose must show the string value rather than an enum object representation.

**Owned changes:** Existing `facts_codec._record_string` and `freeze_value` canonicalize open wire strings. Closed EvidenceClass and other domain enum decoders retain their nominal types. The existing widening field formatter prints canonical string values. No generic conversion framework, hash algorithm change, weakened authentication, new resolver authority, schema/Target/receipt edits or cap/baseline increase.

**TDD sequence:**
1. Run the existing scoped-proof fixed digest, unaffected nested PASS and rename prose regressions before product changes. Add a real before/after JSON proof identity control and open-string ingress controls; inspect hosted RED.
2. Compare the same existing tests on final Wire `7b2a14de58eb18be716c8eadef5c43928ec464a5`, Graph and Graph+Version to locate the regression.
3. Normalize only actual wire string ingress and human widening field text. Keep all historical expected proof IDs and PASS expectations unchanged.
4. Run complete scoped-proof/rename/widening/facts-codec/Graph regressions, strict Mypy/Ruff/hygiene, actual own validation and individual unresolved/partial/type-position deltas. No debt may hide behind aggregate improvement.
5. Freeze a clean independent product ref on5933 for parent integration and independent Astra review. The Demo owner independently checks Compass/Nest with this narrow overlay.

**Hard gates:** Historical `DEPENDENCY-PROOF-e7455e745c3a5c89` remains exact; pre/post-JSON binding IDs match; changed evidence/runtime/imports still revoke proofs; unaffected nested scopes retain PASS; existing serialized data and widening text remain stable. Diagnostics files never enter this branch.
