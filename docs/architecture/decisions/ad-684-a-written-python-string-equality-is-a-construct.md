# AD-684: A written Python string equality is a construct

## Status

Accepted for the Python survey.

## Decision

The survey records `==` and `!=` when either adjacent operand is a written string or bytes
literal. A chained comparison has one fact for the comparison expression. Each fact names its
lexical owner and file and line.

Any comparison, pattern match, call, or reference to a string-comparison method makes this
construct capability partial for the scan. A selected fact still fails the rule; absence is
not proved until the other forms are read.

## Reason

A constant can be passed by name, a literal can occur in a collection or pattern, and a saved
`startswith` method can compare without a written equality. The scan has no proof of those
forms yet. A scan-wide partial statement can hold an unrelated rule, but cannot hide a
comparison by claiming a complete inventory.

## Checks

`tests/test_cli_python_profile_limits.py` covers both operators, a chain, absence, a named
constant, membership, a method and a pattern. Python 3.12 confirms the written AST forms.
