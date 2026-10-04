# AD-14 The report headline follows its verdicts, never the exit code alone

`report` exits 0 whenever its observation is complete, so the exit code cannot say whether rules
hold. Its terminal and HTML banner follows `declared_rules`; open pairs remain context. Incomplete
evidence is NOT CHECKED. A completed diagnostic `validate` shows FAIL for a rule violation and
REJECT otherwise. `check` reads all five verdicts; `init` keeps its headline. Observation format
and exit codes stay unchanged; command-result v3 is separate. Reason: a headline must not say PASS
above a FAIL or NOT CHECKED verdict. Check: render tests for report, check, validate and init.
