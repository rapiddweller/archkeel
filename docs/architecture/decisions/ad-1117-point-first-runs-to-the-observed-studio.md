# AD-1117 Point first runs to the observed Studio

**Status.** Accepted. Builds on AD-638 and AD-1017. Part of #687.

**Decision.** The no-init refusal names `archkeel studio --root PATH` as an option to inspect the
observed structure without a contract. The onboarding guide puts that option before drafting.
The command still refuses the requested validation or report and writes no contract.

**Reason.** The contract-free Studio already exists, but the no-init message only named `init`
and `validate`. A newcomer can inspect the source before deciding the target architecture.
Layout groups are not approved components. Missing evidence is not proof of absence.

**Limit.** This does not add entry-point discovery or prove 800×600 usability.
Those parts of #687 are tracked in #2040 and #2041. The frame and its verdict do not change.

**Tests.** `tests/test_cli_auto_init.py` checks both commands, both opt-outs and the real CLI.
