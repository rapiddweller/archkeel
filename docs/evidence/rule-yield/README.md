# Historical version 1 rule measurements (#218)

Observed 2026-10-02 with Python 3.11.12, three sequential scans per runtime.
[Measurements](measurements.json) contain every rule, UNKNOWN cause, digest and
profiling overhead. [Classification](classification.json) compares raw findings.
These artifacts measure the earlier #205 candidate, not current main. The
[version 2 command](../../rule-yield.md) now captures boundary population receipts,
true passes and separate global API limits; repeat it for each pinned installation.

| Input | Pin |
|---|---|
| Released analyzer | `archkeel==0.8.4`, analyzer 0.63.0; identical digest to base `50e552b` |
| Corrected candidate | #205 `12bfac1cf742a8ca50633cb755b77135cee3ff79`, analyzer 0.64.0 |
| CE snapshot | `a510148f2c0472601decd92b6898669d90ce4e12`; snapshot of the earlier working tree, not a released CE revision |
| EE snapshot | `c9f80e8c0173ba7db3248c7b08223c570afbfbe7`; committed source `dc752659` plus current contract/config/provenance only |

| CE boundary rule | VIO unchanged | UNKNOWN records old → candidate | Warm replay seconds old → candidate |
|---|---:|---:|---:|
| AUTHORING-API-TYPES | 1 | 5 → 5 | 0.270 → 0.316 |
| DOMAIN-API-TYPES | 35 | 64 → 53 | 0.273 → 0.322 |
| DSL-API-TYPES | 10 | 71 → 70 | unavailable: isolated replay changes findings |
| IO-API-TYPES | 33 | 45 → 45 | 0.257 → 0.290 |
| RESOURCES-API-TYPES | 0 | 1 → 1 | 0.236 → 0.273 |
| RUNTIME-API-TYPES | 23 | 22 → 22 | 0.251 → 0.289 |

CE retains 102 violations and identical coverage (492 parsed files).
Total UNKNOWN records fall 216 → 204: twelve position records disappear; four
retained records change their nested cause to unresolved `timedelta`.
No new violation needs classification: true positive 0, false positive 0, disputed 0.
Existing violations were not reclassified. Version 1 did not capture decided passes.

EE retains 88 violations, eight non-boundary UNKNOWNs and identical coverage
(1129 parsed files). Its 23 rules declare **no boundary_types policy**; this measures
existing rules, not EE boundary yield. There are no new EE violations to classify.

Median scan seconds: CE 7.240 → 7.295; EE 11.438 → 11.929. Warm replays include
dispatch, shared setup and profiler overhead; timings are not exclusive or additive.
These sequential local runs on a shared developer machine cannot establish a speed change.

The bounded datetime candidate is worth retaining: it removes twelve existing
UNKNOWN records under unchanged policy while [synthetic controls](controls.json)
keep external and shadowed types UNKNOWN and the neighboring `object` violation.
Its source diff is 219 additions / 37 deletions across five files, including binding
proof. This supports #205; it does not justify general resolver expansion.

Reproduce each pin with its isolated installation using the
[measurement command](../../rule-yield.md). Compare `violations` in the raw companion
observations by record ID and contents; review any added finding with its cited source.
These local source snapshots and their provenance must be retained to repeat this run.
Post-blocker release, explicit EE boundary policy and unsupported predicate pass/runtime
evidence remain pending.
