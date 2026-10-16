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

## Observed RED

Hosted38957724507: the same untouched three regression tests pass on Wire7b2a (3/3), fail on Grapha4a8 (3/3) and fail identically on Graph+Version5933 (3/3). Hosted38957972549/job117165533576 runs the complete scoped/rename tests with new ingress controls:18 failed/62 passed. Open record fields preserve DecisionMaker and ArchitectureRuleKind wrappers. The actual Observer already returns a canonicalized model with historical binding e7455e745c3a5c89, and JSON replay agrees; the earlier Core-issued receipt incorrectly contains d8dff006365e7496. Issuance calls the same parse_record/freezing port before its final JSON boundary. No historical expected value changes.

## Focused GREEN

Hosted38958355251/job117166813306:80 scoped-proof/rename tests pass with every historical expected digest and PASS unchanged. Actual Core-issued, returned-model and JSON-replayed IDs all equal DEPENDENCY-PROOF-e7455e745c3a5c89; all record repr values agree. Closed EvidenceClass remains nominal while both open string fields and recursively frozen JSON values are exact str primitives. Mypy checks139 source files, Ruff and11 hygiene tests pass. The canonical wire-byte assertion and final exact-source site gate remain part of the freeze verification. Demo verification is owned independently; no Demo expectations or fixtures are edited here.

## Review boundary control

Parent identified that str(raw) can invoke a decorated __str__ on an otherwise valid str subclass, while JSON writes its actual Unicode characters. Add a real subclass fixture to the existing primitive/wire-byte control and actual component-field widening text. Observe those failures before replacing only the same three conversions with explicit base-string character extraction. Do not broaden the wire normalizer or touch hashing policy.

Review RED:38959214039/job117169747162 proves both decorated-string regressions on the unchanged first fix:2 failed/80 passed. Use the explicit base str.__str__ character operation at the existing ports, retaining ordinary values and owned StrEnums. The first native site gate additionally catches52→53 typing positions from the unnecessary object-parameter formatter helper despite no new UNKNOWN/call sites. Remove that new API: map both values through one local formatting expression in the existing field classifier; no cap increase or imprecise annotation.
