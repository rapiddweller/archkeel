# AD-117 Report verdicts require evaluator evidence

An empty finding list does not prove a rule ran (#159, #160).

The analyzer records each supported evaluator's actual scope and selected facts. The report
projects those receipts, violations and shared UNKNOWN counts into typed rule rows. No receipt
means UNKNOWN, not PASS. Permissions remain declarations. A failed rule retains its undecided
positions; filtering UNKNOWN includes that mixed result without hiding its failure.

An explicit, read-only baseline reuses the existing fingerprints, occurrence counts and cycle
contraction logic. It never changes the observation or overall verdict. Resolution requires a
current rule with complete evaluation evidence and no undecided positions. A removed rule, an
incomplete scan or partial type evidence cannot prove old debt resolved. Repeated occurrences
share a group count; the report does not claim which individual line was already known.

Keep the diagram primary. Reuse native tables, details and filters; no second report framework.
Focused CLI views remain focused. Without JavaScript, all static evidence stays readable.
