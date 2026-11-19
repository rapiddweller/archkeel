# AD-940 Python parse failures live with parser problems

**Decision.** Keep `ParseFailure` and its `From<Problem>` implementation beside
`Problem` in the limits module. Keep the existing path through `parse` for callers.

**Reason.** The parser root orchestrates the checks. It does not need to own the
traits that convert and print an error. Those traits gave the checks a possible
return path through the parser root.

**Rejected.** Remove `From<Problem>` or change error selection to avoid the cycle.
Callers need the conversion and the selected exception, line and message.

**Limit.** The tokenizer limits, error selection, and verdict handling stay the
same. This change removes only the module cycle holds in the Python parser group.

**Tests.** The Python parser and collector tests check the error results. The
native self-scan checks the effect on both cycle rules.
