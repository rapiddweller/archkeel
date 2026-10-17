# Native assessment test consumers

The final Boundary-Reasons full suite reported two failures in unchanged test
consumers. The same tests are byte-identical at the earlier reviewed f638 union.

The through-enforcement test still imports a removed private requires_covers
alias. Core now imports the shared requires_import_assessment port, which handles
exact symbol evidence and UNKNOWN. Pin that actual shared identity and retain
the real native import findings and projection assertions.

The module-object-grant evaluator control expects the old private undecided
spelling. The actual internal API returns AssessmentStatus.UNKNOWN. Pin that
nominal identity and preserve its one-row and unknown-name evidence conditions.

First run both untouched tests with the actual f638 production and require the
same two failures. Then run both corrected existing test files with unchanged
current production, Ruff and related exact-requires regressions. No production,
wire behavior, Target, baseline, threshold or end-to-end assertion is changed.
Independent Astra review precedes integration after the exact-requires API.
