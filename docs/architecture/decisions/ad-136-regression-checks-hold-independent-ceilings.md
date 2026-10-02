# AD-136 Regression checks hold independent ceilings

Keep the existing conservative policy: every measured regression count and unresolved-call
share must not increase. Neither offsets the other. This checks declared change limits;
it does not rank architectures or claim that a refactor is worse overall (#215).

The observations must have complete coverage and matching schema, scope, analyzer digest
and contract. Missing or inconsistent evidence stays UNKNOWN. A profile's unmeasured count
and its ratio stay `n/a`, even when a call total exists. New undecided positions cannot be
hidden by fewer calls; existing UNKNOWNs do not become proven closure.

Both historical counterexamples deliberately reject under this policy:

| Source change | Before | After | Rejecting ceiling |
|---|---|---|---|
| `5a07aed` | 484 / 2511 | 466 / 2395 | Share increased despite fewer unresolved calls |
| `bbab17c` | 474 / 2309 | 479 / 2348 | Count increased despite a lower share |

These are saved `fixtures/D-self/result.json` values at each commit and its parent.
The tests replay both directions and retain the raw counts/fractions. Integer cross-products
avoid rounding. Weighted scores and an automatic “net improvement” judgment were rejected.
Duplicate removal may require a human policy decision; it must not silently bypass a ceiling.

`tests/test_ratchets.py` covers the historical cases, unmeasured ratios and new UNKNOWNs.
`make demo` retains the real revision-check example: unchanged violation fingerprints cannot
hide rising unresolved calls or their share. Baseline equality under `validate` is unchanged.
