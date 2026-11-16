# AD-658: A Python assert is a written construct

## Status

Accepted for the Python import survey.

## Decision

The Python collector writes each `assert` statement as a construct with its lexical owner and
file and line evidence. It states support for `assert`, not for other construct kinds.
Existing gaps that can hide code continue to hold each construct rule that reads the code.

## Reason

An `assert` statement is visible in the parsed Python tree without resolving a name. A rule can
therefore decide whether a fully read source contains it. `exec` can execute an assertion in text
that the scan cannot see, so the existing dynamic-code gap still holds the rule.

## Checks

`tests/test_cli_python_profile_limits.py` checks a present assertion, an absent assertion and an
assertion hidden in dynamically executed text through the release core.
