# AD-997: Type-ignore sites include dotted member calls

## Status

Accepted. Part of #1537. Extends AD-780, AD-868 and AD-990.

## Decision

Record a trailing type-ignore comment on a single-line call with a dotted name, such as
`handle.inner.close()`. Each part of the name must be a written ASCII identifier.
Keep the exact owner, line, statement and tag for the existing allowance check.
The survey does not resolve the called member. Computed targets and multiline calls stay partial.

## Reason

An additional member access does not change where the parser attaches the comment.
An allowance still permits only the reviewed site.

## Rejected

Do not match the last member alone. Two calls can name the same member on different receivers.

## Checks

`tests/test_cli_python_type_ignore.py` uses copies of the newer-syntax demo.
An exact allowance passes its rule. A different statement or tag fails it.
Multiline and computed calls stay UNKNOWN. A string is not a comment.
The call-owner rule still fails at `sample/report.py:9` in all copies.
