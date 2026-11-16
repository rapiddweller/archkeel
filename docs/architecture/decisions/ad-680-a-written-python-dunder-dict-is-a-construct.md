# AD-680: A written Python dunder dict is a construct

## Status

Accepted for the Python survey.

## Decision

The survey records each written `.__dict__` attribute, with its owner and the attribute's
file and line. Multiple attributes in one chain each have their own evidence.

If the scan contains any call, the `dunder_dict` capability is partial. A call can read the
attribute through a computed name or an alias; the scan does not yet prove the target or its
attribute argument. A rule that reads it cannot prove absence. Other construct capabilities
are not held by this partial statement.

## Reason

`getattr(obj, "__dict__")` and a call to a saved `getattr` read the same attribute as a written
access. Counting only written attributes as a complete inventory could therefore give a false
PASS. The scan-wide partial statement is conservative: even an unrelated call holds the rule.

## Checks

`tests/test_cli_python_profile_limits.py` covers a written access, chained accesses, absence,
computed reads and a saved builtin. Python 3.12 confirms the computed and saved reads.
