# AD-634: Python scans select a target version

**Status:** Accepted. Closes #1316.

## Decision

The Python collector reads a target version, not an interpreter.
`[scan] python` selects the target. Otherwise, the lowest declared `>=` version selects it.
If no project requirement exists, the collector selects its default.
The supported targets are Python 3.11 through 3.14.
The parser and the store use the standard-library table and grammar of the selected version.
The run summary states the target and its source.

## Reason

The native collector does not run Python. A Python interpreter on `PATH` cannot select its grammar.
The intersection of standard-library tables makes a version-specific standard name look external.
The union can hide an external dependency on a target where the name is not standard.

## Limits

The collector refuses an unsupported target and names the supported range.
It refuses a requirement form whose lower bound it cannot read.
An invalid requirement or a requirement mismatch remains a gap.
The scan verifies the target again after collection.

## Checks

`test_python_target_is_selected_from_the_project_requirement` checks the reported UX case.
The target, grammar, and standard-library CLI plants check selection, refusals and facts.
