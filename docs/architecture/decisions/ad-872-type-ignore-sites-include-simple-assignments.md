# AD-872: Type-ignore sites include simple assignments

## Status

Accepted. Part of #1537. Extends AD-780 and AD-868.

## Decision

The Python survey records a type-ignore comment on a single-line assignment to one name.
The fact keeps the exact statement, owner, line and tag for the existing allowance check.
Multiline assignments, multiple targets and multiple statements on one line stay partial.

## Reason

The parser identifies the assignment target and the comment without resolving either value.
The statement bytes identify the allowance site. The rule needs no builtin identity premise.

## Checks

`tests/test_cli_python_type_ignore.py` covers simple assignments, exact allowances, strings,
multiline statements and multiple targets or statements.
