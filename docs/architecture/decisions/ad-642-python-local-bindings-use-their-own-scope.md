# AD-642: Python local bindings use their own scope

**Status:** Accepted. Part of #880.

## Decision

The import hazard survey reads lambda parameters and assignment expressions in the lambda scope.
It reads lambda defaults in the enclosing scope.
Function locals include exception targets and all match capture forms.
Function parameters, assignments, loop targets and context manager targets use the same binding
inventory.
An explicit `global` stops lookup in enclosing function scopes.
A `nonlocal` name resolves in an enclosing function scope.

## Reason

Python does not resolve a local binding as a standard library module of the same name.
Treating it as a module creates an import-system gap and holds rules that can otherwise pass.

## Alternatives and limits

AD-628 keeps an import binding of the same name anywhere in the file conservative.
This decision keeps that limit, because an assignment can propagate a module object.
The survey does not infer values from arbitrary assignments or calls.
Module and class bodies have execution-order lookup and do not use function-local rules.
Their bindings can retain an import-system gap until the survey proves execution order (#1360).
A possible class binding or class `global` blocks an enclosing function-local proof.
Functions, lambdas and comprehensions do not inherit a class namespace.

## Checks

`local_binding_forms_are_not_module_references` tests each form and retained module gaps.
`test_local_bindings_match_python312` checks the plants with Python 3.12 and the CLI.
`test_module_and_class_bindings_keep_gap` checks the retained gap with Python 3.12.
