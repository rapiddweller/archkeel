# AD-990: Type-ignore sites include direct calls

## Status

Accepted. Part of #1537. Extends AD-780 and AD-868.

## Decision

The Python survey records an exact type-ignore comment on a single-line `name(...)` call.
The name must be an ASCII identifier. The call can have positional and keyword arguments.
The fact keeps the exact owner, line, statement and tag for the existing allowance check.
Multiline calls, multiple statements and computed call targets stay partial.

## Reason

The parser identifies the written call and comment without resolving the called name.
A shadowed name does not change whether the comment is present.
The statement bytes identify the allowance site. No binding identity premise is needed.

## Checks

`tests/test_cli_python_type_ignore.py` checks calls, allowances, strings, shadowing,
multiline calls, multiple statements and computed targets.
