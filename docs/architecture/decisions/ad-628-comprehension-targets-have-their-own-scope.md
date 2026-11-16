# AD-628: Comprehension targets have their own scope

**Status:** Accepted. Part of #880.

## Decision

The Python import hazard survey treats comprehension targets as local names.
The first iterable is read in the enclosing scope.
The targets, later iterables, conditions and result expressions are read in the comprehension scope.
An import binding with the same name anywhere in the module still keeps the conservative gap.
An actual `site` import remains an import-system gap.

## Reason

Python binds comprehension targets in their own scope.
Treating a local name as a standard-library module gives a false import-system gap.
The first iterable is evaluated outside the comprehension scope.

## Alternatives and limits

Dropping all hazards named `site` could hide a real import-system change.
Tracking values through arbitrary assignments is not part of this decision.
Ambiguous import bindings remain gaps.

## Checks

`survey::hazards::tests::comprehension_targets_shadow_module_names_only_in_their_scope` checks
local targets, enclosing reads and the real module.
`test_comprehension_local_has_no_import_gap_but_site_module_does` checks the CLI verdict.
Python 3.12 confirms the target shadows the module without changing the enclosing binding.
