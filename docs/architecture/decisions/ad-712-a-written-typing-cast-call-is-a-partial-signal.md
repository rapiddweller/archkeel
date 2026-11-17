# AD-712: A written typing cast call is a partial signal

## Status

Accepted for the Python survey.

## Decision

The survey records a `cast_call` signal for a direct call through a uniquely bound import of
`typing.cast` or `typing_extensions.cast`, including direct module aliases. The signal names
its lexical owner and written callee. It states the written form, not that runtime code has
left the function unchanged.

The capability is partial: saved functions, rebound names, and indirect calls remain unread.
The collector's validation table admits only a partial claim. An unseen cast cannot produce a
PASS from this capability.

## Checks

`test_cli_python_profile_limits.py` checks direct and aliased calls, both typing modules, a
rebound name and an unknown callable. The collection test refuses a supported capability.
