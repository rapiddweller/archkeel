# AD-706: A direct builtin import call is a construct

## Status

Accepted for the Python survey.

## Decision

A direct call of an unshadowed builtin `__import__` or a uniquely bound, directly imported
`importlib.import_module` writes a `dynamic_import` typing signal.
This is independent of the import survey's edge or gap for the call. Literal calls keep their
static edge, and calls with an unknown target keep their every-module gap.

The capability is partial: saved builtins, rebound names and other loader call forms are not
all resolved. An absence cannot pass a rule. The collector's protocol 11 validation table
admits only a partial capability. The importlib form records the written import and call; it
does not prove that runtime code has not replaced the imported function.

## Checks

`test_cli_python_profile_limits.py` checks literal and variable calls, both importlib forms,
aliases, a saved builtin, a shadowed name and an empty case. The collection test refuses a
supported capability.
