# AD-928 The renderer does not own frame results

**Decision.** Keep the writer's frame and error types in `engine_frame.output`. Keep the
writer's public paths and output bytes. The renderer continues to read JSON, not the
writer's result types. Remove `Clone`, `Debug` and equality from `Outcome`: production
callers read its decision and violations and do not use these traits.

**Reason.** The renderer sits below `engine_frame` in the module tree. Keeping the
writer's traits in that parent let possible execution close a component cycle. The
evaluator had the same problem with `Outcome` in its crate root. Its tests can print
the decision directly.

**Rejected.** Exempt trait execution from the cycle rules, or put the writer and the
renderer in one component. Both options hide a dependency that can matter in other code.

**Limit.** The output types still have traits that their callers need. Moving them
changes the module names in the scan inventory and can expose candidates at the
new path. The module cycle rule still has possible return paths.

**Tests.** The native self-scan checks the component rule. The CLI control in
`tests/test_cli_report_explain.py` adds a known return edge between two components
and checks that the rule changes from PASS to FAIL with both edges cited.
