# Measurement control types — issue #542

Approved by the coordinating agent after Command draft PR575 and its final seven green gates. Base 3dd2efdc54ef99f2b4cb742f3194cfd1f2619a84; remote GitHub/Actions only. Execute Superpowers plan/TDD/verification inline, freeze for independent Astra review before merge.

## Responsibilities and compatibility

- Existing ir.measurements remains the owner of MeasurementBudget, Measurements, validation and comparison. It owns MeasurementBudgetName (six eligible scalar selectors), NameBudgetKind (facade/coupling name sets), MeasurementResolution (measured/n/a) and MetricComparisonStatus (PASS/FAIL/n/a).
- MetricComparisonStatus is distinct from model.ComparisonStatus (SUPPORTED/UNKNOWN); Delta comparison/version migration is a later independent stage. Profile.UnmeasurableScalar keeps its existing four capability values and import direction.
- Precisely type MeasurementBudget.name, Measurements.resolution, ContractMeasurementBudget.name, InterfaceBudgetResult.budget and the actual status in compare_measurements return tuples. Preserve tuple compatibility; no new DTO framework/module.
- Valid legacy strings normalize at actual existing DTO boundaries. Codec budget/measurement tag helpers convert raw input once; retain supported baseline/lock payload versions, count/ratio validation, errors and zero/None distinctions.
- Budget labels are presentation data. Decisions use owned nominal names. JSON field names, module/pair identities, free actors and open DeltaWireSemanticChange.dimension/change remain data.
- Migrate only the owner and actual codec/model/check/interface/summary consumers. No broad new Budget port, baseline allowance, per-enum module, duplicated backend status in render, or decoder framework.
- Whole measurements native guard is honest. Mixed governance codec retains unrelated pending version grammars under542; protect actual migrated tag decisions with source-backed bounded controls rather than claim whole-codec absence or invent a permanent parser exception.

## Test first

1. Author independent Target entities for real enum/DTO/field/return ports plus native field/return widening, enum substitution and raw equality/membership/match/Final-alias controls.
2. Hosted native RED before production, using actual source modules/selected model declarations rather than observation-derived JSON.
3. Implement the four domains and necessary producers/consumers only. Preserve valid/invalid legacy budgets, sorted unique keyed names, boolean/negative counts, zero/None availability, exact errors and historical wire bytes.
4. Focused measurement/ratio/facade/baseline/contract/lock/null-profile regressions, strict Mypy, Ruff and hygiene.
5. Actual own baseline plus normal receipt and committed NoWrite; compare precise UNKNOWN IDs and unresolved/PARTIAL call AST/target/reason/multiplicity against actual predecessor. No debt or budget rise.
6. Clean freeze, measured source cost and final independent Astra review. Stop before Delta.

Estimated production scope: measurements.py, codec_governance.py, model.py, check/ratchets.py, check/validation/__init__.py, ir/interfaces.py, render/summary.py. Existing passthrough baseline/renames/widening need no speculative edits. Expected30–80 net source lines; actual costs will be reported. Necessary extra consumers require evidence, not widening.

Native RED38979373233/job117236357495 observed35 failures/10passes on unchanged production: missing/loose nominal domains, actual Target mismatches and legacy outputs not yet normalized. The baseline byte-control test was corrected to call the existing baseline_bytes(violations,budgets) API; its RED assertion already failed before that call, so this changes no production expectation.

Native positive-fixture diagnosis found one over-specified module visibility assertion (not a field/return/type failure): module Visibility is unavailable in Source. The authored owner anchor now follows existing module anchors without a visibility requirement; actual module publication remains in the existing governance public contract. All class/field/type/return intent stays fixed; no Source resolver or authority change.
