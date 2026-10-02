# AD-140: Measure rule evidence without inventing passes

## Decision

An optional `make rule-yield` tool measures clean pinned Python repositories.
Reuse the existing scan and evaluators. Keep timings outside canonical IR.
Report findings, UNKNOWN causes and available position totals; missing decided
passes remain `null`. A violation and UNKNOWN can share one position.

Capture original evaluator inputs in a separate profiled scan. Replay each rule
independently with the same source facts and scope. Publish its warm runtime only
when findings match the original evaluation. Dependent proof can prevent replay;
that runtime stays unavailable. Profiling overhead is explicit, never subtracted
to invent exclusive or additive time.

## Why and limits

UNKNOWN counts and resolver size alone do not measure useful decisions or cost.
A global resolver API, new IR schema and metric CI gate add unevidenced complexity.
This observational tool adds none of them. It supports Python only.

The baseline and candidate retain source, policy and Python identity. The released
0.8.4 analyzer and the chosen base have identical digests. EE's current contract
has no boundary rules; no EE boundary yield is claimed. Post-release acceptance
and a complete pass ledger remain open (#218).

## Evidence

`tests/test_rule_yield.py`; [command and limits](../../rule-yield.md);
[pinned measurements](../../evidence/rule-yield/README.md).
