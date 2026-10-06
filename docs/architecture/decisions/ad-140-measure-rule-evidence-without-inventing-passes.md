# AD-140: Measure rule evidence without inventing passes

## Decision

An optional `make rule-yield` tool measures clean pinned Python repositories.
Reuse the existing scan and evaluators. Keep timings outside canonical IR.
Report findings, UNKNOWN causes and existing aggregate assessment statuses.
Capture boundary producer verdicts and population receipts. Count passes only when
the population reconciles and violation and undecidability are both absent;
accepted allowances count separately. A violation and UNKNOWN can share a position.
Keep symbol/occurrence and inherited origin identities; add receipt-only ambiguity.
Non-boundary or unreconciled positional passes remain `null`.
Existing dependency/interface generators and requires predicates expose import verdicts.
Keep import IDs and scope; require generator completion and published evidence.
Requires binds existing import FACT receipts after the original filters.
Observed passes never close an unowned facade scope or alter its UNKNOWN assessment.
Per-rule import predicates are not unique repository import counts.
An empty observed import population has zero passes, never an aggregate PASS count.
Other supported evaluators decide one observed-scope conjunction. Bind the actual
producer, published receipt, module facts, evidence, scope and original findings.
Complete safe scopes pass once; violations make the conjunction false while UNKNOWN
causes stay visible. Missing proof keeps counts unavailable; partial scans never pass.
Permissions remain declarations. Scope, type and import units are never summed.

Copy original evaluator inputs/results before private import proof is stripped.
Capture them in a separate profiled scan. Replay each rule
independently with the same source facts and scope. Publish its warm runtime only
when findings match the original evaluation. Dependent proof can prevent replay;
that runtime stays unavailable. Profiling overhead is explicit, never subtracted
to invent exclusive or additive time.

## Why and limits

UNKNOWN counts and resolver size alone do not measure useful decisions or cost.
The tool supports Python only, without a global resolver API, new IR schema or metric CI gate.

The baseline and candidate retain source, policy and Python identity. The released
0.8.4 analyzer and the chosen base have identical digests. EE's current contract
has no boundary rules; its boundary yield is N/A without changing policy. Full acceptance
and missing producer/runtime evidence remain open (#218). Population
reconciliation is distinct from scope closure: unresolved routes and unscoped API
limits stay explicit. Global API limits are not blamed on every boundary rule.

## Evidence

`tests/test_rule_yield.py`; [command and limits](../../rule-yield.md);
[pinned measurements](../../evidence/rule-yield/README.md).
