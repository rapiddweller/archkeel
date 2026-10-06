# AD-106: A baseline entry names its violation in any subject order

Build observation and baseline fingerprints from sorted rule IDs and subjects,
retaining multiplicity. Subject order carries no direction; roles do.
This prevents renames from turning unchanged violations into new/resolved debt.

Duplicate canonical entries remain invalid. Unreadable baselines require manual
correction. A refused write explains refusal and `--accept-new`, never recommending
the command it refused. Fingerprints and file format stay compatible.

[Baseline proof](../../../tests/test_baseline.py).
