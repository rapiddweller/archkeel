# AD-908: Type-ignore sites include return statements

## Status

Accepted. Part of #1537. Extends AD-780, AD-868 and AD-872.

## Decision

The Python survey records a type-ignore comment on a single-line return with a value.
The fact keeps the exact statement, owner, line and tag for the existing allowance check.
Multiline returns and multiple statements on one line stay partial.

## Reason

The parser identifies the return and the comment without resolving the returned value.
The statement bytes identify the allowance site. No builtin identity premise is needed.

## Checks

`tests/test_cli_python_type_ignore.py` covers returns, exact allowances, strings,
multiline statements and multiple statements.
