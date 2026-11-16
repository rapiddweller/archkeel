# AD-666: A Python broad exception handler keeps unread types partial

## Status

Accepted for the Python survey.

## Decision

A bare handler, or one that includes the visible builtin `Exception` or `BaseException`, is a
`broad_except` construct. Each fact names its lexical owner and file and line. The collector
states the construct supported only when every handler is proven broad. An unproved handler type
leaves the capability partial for the scan; a rule that reads it cannot prove absence.

## Reason

An exception type can be an alias or the result of a runtime expression. The written `ValueError`
can also have been rebound, and a project class can resolve to `Exception`. A spelling alone is
not a proof that a handler is narrow. A file-wide binding check conservatively withholds the
builtin proof when any scope binds its name.

The partial statement is scan-wide, so an unrelated unproved handler can hold a rule. It does not
hold rules that read other constructs. A seen, selected broad handler still produces a violation.

## Checks

`tests/test_cli_python_profile_limits.py` covers bare and named handlers, tuples, an alias and
an unread narrow spelling. Python 3.12 confirms the caught exceptions.
