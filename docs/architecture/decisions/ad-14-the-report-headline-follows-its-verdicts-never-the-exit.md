# AD-14 The report headline follows its verdicts, never the exit code alone

`report` exits 0
whenever its observation is complete, so the exit code cannot say whether rules hold. The terminal
and HTML headline come from one summary: NOT CHECKED on exit 2, FAIL when `declared_rules` is
FAIL, NOT CHECKED when a completed `report` or `validate` leaves them UNKNOWN, otherwise PASS.
`check` likewise reads all five verdicts instead of its exit code; `init` keeps its headline. No
exit code or result field changes. Reason: a headline must not say PASS above a FAIL or NOT CHECKED
verdict. Check: the render tests for report, check, validate and init headlines.
