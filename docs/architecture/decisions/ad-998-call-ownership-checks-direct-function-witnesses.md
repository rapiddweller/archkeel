# AD-998: Call ownership checks direct function witnesses

## Status

Accepted. Part of #613 and #619.

## Decision

The linked Python collector ties a direct name at a call site to a stable top-level function.
The witness names the call, the declaration and the direct import, if there is one.
The store checks those links against the typed records.
Saved replies cannot supply a witness.

The evaluator reports a proved call outside its permitted scope as FAIL.
An unrelated open call does not hide that violation.
PASS needs a target declaration and a complete written call count in each non-exempt module.

## Reason

A call candidate is not proof of what a name binds.
A computed provider write can leave the old candidate visible after Python replaces the name.
The collector withholds witnesses when the source scan is incomplete.

## Limits

This slice selects module and package scopes. It keeps the lexical scopes for caller permissions.
Computed targets, receivers, non-direct imports and calls outside the admitted bodies stay open.
The collector does not prove that execution reaches a written call.

## Checks

`tests/test_cli_python_call_owner.py` uses the unchanged newer-syntax demo and independent controls.
It checks the call inside the generator, an allowed scope, a callback and a computed provider write.
The original #737 test expected the report call to fail and the exact type-ignore rule to pass.
