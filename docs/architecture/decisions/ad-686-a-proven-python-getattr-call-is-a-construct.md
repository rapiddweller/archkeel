# AD-686: A proven Python getattr call is a construct

## Status

Accepted for the Python survey.

## Decision

The survey writes a `getattr_call` typing signal for a bare call of the builtin `getattr`
when no binding in the file can hide it. The signal names its lexical owner and file and line.
The `typing_signals` section states the signal; the capability states only `getattr`.

A reference to `getattr` or an unproved call makes the `getattr` capability partial for the
scan. A selected proven call still fails a rule that forbids it.

## Reason

`f = getattr; f(obj, name)` calls the builtin without spelling it at the call. An unknown
callable can also hold it, and a rebound `getattr` is not proven to be the builtin. The
file-wide binder check withholds the builtin proof when any scope binds its name.

The partial statement is scan-wide, so an unrelated call can hold this rule. No other typing
signal or construct is declared complete by this decision.

## Checks

`tests/test_cli_python_profile_limits.py` checks a direct call, absence, a saved builtin,
a rebound name and an unknown callable. Python 3.12 confirms direct and saved calls.
