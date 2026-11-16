# AD-682: A proven Python vars call is a construct

## Status

Accepted for the Python survey.

## Decision

The survey records a call of the bare builtin `vars` when no binder in that file can hide it.
Each fact names its owner and file and line. A reference to `vars` or an unproved call makes
the `vars` capability partial for the scan.

## Reason

`f = vars; f(obj)` calls the builtin without spelling it at the call. A parameter or another
callable expression can also hold it. A rebound `vars` is not proven to be the builtin.
The file-wide binder check withholds a proof if any scope binds that name.

The partial statement is scan-wide, so an unrelated call can hold this construct rule. A
proven, selected `vars` call remains a violation. Other construct capabilities are unchanged.

## Checks

`tests/test_cli_python_profile_limits.py` covers a direct call, absence, a saved builtin,
a rebound name and an unknown callable. Python 3.12 confirms the direct and saved calls.
