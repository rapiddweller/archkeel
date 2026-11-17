# AD-706: A direct builtin import call is a construct

## Status

Accepted for the Python survey.

## Decision

A direct call of an unshadowed builtin `__import__` writes a `dynamic_import` typing signal.
This is independent of the import survey's edge or gap for the call. Literal calls keep their
static edge, and calls with an unknown target keep their every-module gap.

The capability is partial: saved builtins, rebound names and other loader call forms are not
all resolved. An absence cannot pass a rule. The store and the protocol 11 validation table
admit only a partial capability.

## Checks

`test_cli_python_profile_limits.py` checks literal and variable calls, a saved builtin, a
shadowed name and an empty case. The store test refuses a supported capability.
