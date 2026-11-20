# AD-1005 The gallery counts rule results and shows missing decisions

## Decision

The capability page uses the self and showcase frames that produced the gallery reports.
It also runs the separate Report Explorer contract. The system verdict covers its declared parts.
It groups rule results by kind and lists each rule with its run, scope, decision and premises.
It shows a declared rule without a result and the reason when available.
Intentional counterexamples have separate counts.
The Explorer architecture check exits unsuccessfully on a rule violation.

## Reason

The shop demo declares rules that currently have no evaluator result.
Counting only returned decisions would hide those rules.
A rule result gives no count of the source items that the evaluator examined.

## Checks

`tests/test_report_capabilities.py` checks decisions, missing rows, scope, causes and counterexamples.
