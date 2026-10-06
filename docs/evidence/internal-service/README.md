# Onboarding an internal 13-component service

Historical 0.3.0 release evidence from one committed private-service snapshot.
An architect decided an interview target; an independent agent decided a blind
auto target before seeing those answers. This is one experiment, not an auto-mode
accuracy claim.

## Artifacts

- [Interview contract](architecture-contract-interview.json) and
  [report](report-interview.html): architect decisions and their violations.
- [Auto contract](architecture-contract-auto.json) and [report](report-auto.html):
  agent decisions and their violations.
- [Pair comparison](decisions-interview-vs-auto.json): original, final architect
  and agent answers, with basis and confidence.

Both targets rejected the same heavy use-case-to-persistence crossing. Agreement
was scored before the architect reviewed mismatches. Later changed answers cannot
be counted as improved blind agreement.

Artifacts preserve structure, counts, rule kinds, attribution and verdicts.
Names and rationales are anonymized, source lines removed and digests zeroed.
They cannot authenticate or reproduce the private snapshot. Reports were rendered
at `8531bdb` with Python 3.12; old defects and UI behavior are historical.

The run showed why intent must be decided independently of observed imports.
Attribution and nonempty rationales are checkable form; neither proves review or
truth. Match the analyzed project's runtime. Use [onboarding](../../onboarding.md)
for the current workflow and [known limits](../../known-limits.md) for current gaps.
