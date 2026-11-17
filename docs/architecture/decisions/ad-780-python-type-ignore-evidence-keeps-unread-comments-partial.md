# AD-780 Python type-ignore evidence keeps unread comments partial

**Status.** Accepted. Part of #880 and #1537.

**Reason.** A type-ignore rule must find a suppression and must not mistake string text
for a comment. An exact allowance names its owner, line, statement and tag.

**Decision.** The parser supplies comment ranges from its lexer. The survey writes a
type-ignore signal for a simple `name.method()` expression with a trailing, readable
type-ignore comment. It records the exact owner, statement, line and tag. The support
is partial when a type comment remains unread. It is supported when the lexer finds no
unread type comment.

**Limit.** Other statements, standalone comments, and complex tags stay partial. They
cannot make an absence PASS. The parser reads comments inside f-string expressions, but
an unread expression keeps the construct partial.

**Alternative.** Search source text. A string can contain `# type: ignore`, so a text
search is not a proof of a comment.

**Checks.** `tests/test_cli_python_type_ignore.py` checks absence, a string, an exact
allowance, a mismatched tag and unread comments. `parse_tests.rs` checks f-string comments.
