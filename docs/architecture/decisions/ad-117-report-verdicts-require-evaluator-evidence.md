# AD-117 Report verdicts require evaluator evidence

An empty finding list does not prove a rule ran (#159, #160).

The analyzer records each supported evaluator's actual scope and selected facts. The report
projects those receipts, violations and shared UNKNOWN counts into typed rule rows. No receipt
means UNKNOWN, not PASS. Permissions remain declarations. A failed rule retains its undecided
positions; filtering UNKNOWN includes that mixed result without hiding its failure.
An UNKNOWN rule prevents a green report headline even when the aggregate remains PASS.
The summary states that difference; canonical verdicts and exit codes do not change.

Analyzer profile `0.57.0` identifies the new evaluation facts. Observation and contract schemas
stay unchanged; older observations without receipts cannot prove per-rule PASS.

Cycle-scope completeness currently needs recursively covered Python roots. Module-cycle
receipts require the full namespace, even when a smaller component scan may be closed.
Dart and explicit `source_paths` scans retain observed cycle findings but cannot prove this
completeness. Their per-rule result stays UNKNOWN unless a violation proves FAIL.

An explicit, read-only baseline reuses the existing fingerprints, occurrence counts and cycle
contraction logic. It never changes the observation or overall verdict. Resolution requires
complete evaluation of the old subjects under the current rule, with no undecided positions.
Narrowing a rule or scan cannot resolve debt outside that scope. Cycle contraction also needs
coverage of the old cycle's members. A package's own receipt does not cover omitted descendants.
Repeated occurrences share a group count; a mixed fingerprint assigns no old/new line identity.
Only a fully shared fingerprint gets muted rows with KNOWN and FAIL markers. Mixed groups
retain known/new counts without assigning old debt to a particular occurrence.

Resolved means absent under currently evaluated rules, not proof that code was repaired.
Baselines do not store historical rule definitions. Use `validate --against` to check contract
widening; the report does not introduce a second history system.

Keep the diagram primary. Reuse native tables, details and filters; no second report framework.
Focused CLI views remain focused. Without JavaScript, all static evidence stays readable.

Under the architect's evidence-backed budget authorization, the self call budget moves
536 → 562. `validate --against ce089cf` identifies 26 added source operations: analyzer 10
(receipt/physical-scope lookups), check 7 (counting and baseline access), CLI 1 (the explicit
baseline option), IR 2 (subject coverage), render 6 (grouping, filter options and assets).
This is new code, not improved detection on unchanged code. The self scan retains 41 UNKNOWN
positions, 53 typing positions, 0 violations, 0 cycle edges and 0 private crossings. No rule or
violation exemption changes.
