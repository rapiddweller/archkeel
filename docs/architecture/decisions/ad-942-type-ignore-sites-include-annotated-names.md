# AD-942: Type-ignore sites include annotated names

## Status

Accepted. Part of #1537. Extends AD-872.

## Decision

The Python survey records a type-ignore comment on a single-line annotated name.
The annotation can have a value or no value.
The fact keeps the exact statement, owner, line and tag for the existing allowance check.
Attribute targets, multiline statements and multiple statements on one line stay partial.

## Reason

The parser identifies the target and comment without resolving the annotation or value.
The statement bytes identify the allowance site. No binding identity premise is needed.
Treating every annotated target as supported would exceed the tested boundary.

## Checks

`tests/test_cli_python_type_ignore.py` covers both forms, exact allowances, strings,
attribute targets, multiline statements and multiple statements.
