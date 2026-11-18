# AD-868: Type-ignore sites include single-line call arguments

## Status

Accepted. Part of #1537. Extends AD-780.

## Decision

The Python survey records a type-ignore comment on a single-line member call with arguments.
The receiver must be a name. The call must be the only statement before the comment on its line.
The fact keeps the exact statement, owner, line and tag for the existing allowance check.
Other forms, including multiline calls and multiple statements on one line, stay partial.

## Reason

The parser identifies the call and the comment without resolving the receiver or its arguments.
The statement bytes identify the allowance site. No assumption about builtins or imports is needed.

## Checks

`tests/test_cli_python_type_ignore.py` checks positional and keyword arguments, exact allowances,
strings, multiline calls and multiple statements.
