# Full verification repair

**Goal:** Repair the known browser failure, preserve coverage, require CI before
merge, and reach Full verification ≤20 minutes with fast PR checks ≤10 minutes.

**Baseline:** Main `27ba8277`; full run `39917947462`: 42:13, two browser
timeouts. Reduced PR CI passed in 9:07 and did not execute those cases.

**Design:** Reuse the existing Make targets and reusable Full workflow. Keep
normal PRs on the short path; CI and test-infrastructure changes additionally
require Full verification. Reuse immutable test/report inputs, with fresh browser
and mutation state. Fix synchronization from evidence rather than raising limits.

**Constraints:** Preserve test identities, assertions, supported runtimes, trust
boundaries and architecture contracts. No new dependencies or workflow files.
Compare like-for-like timings; macOS results do not prove Windows/Linux budgets.

- [x] Terra: make report readiness explicit before throttling and
  share expensive immutable rendering in `tests/test_own_uml_target.py`.
- [x] Luna: measure repeated setup in `tests/test_typescript_control_target.py`
  and `tests/test_architecture_demo.py`; implement only material improvements.
- [x] Parent: route CI infrastructure changes through Full verification and test
  failed/cancelled/skipped results; require GitHub Actions `check` on Main.
- [x] Parent: measure collector scheduling and report regeneration; remove
  repeated work without dropping evidence or tests.
- [x] Integrate, review independently, run local Make checks and the complete suite.
- [ ] Create the repair PR and inspect its CI.

**Acceptance:** Both throttled views pass; selected failed/skipped/cancelled Full
runs block merge; unchanged test inventory; local checks pass; CI Full is green
within 20 minutes and fast PR checks finish within 10 minutes. Pages publication
on Main remains dependent on a verified run. Merge is a separate final action.

**Risks to verify:** initial browser layout under throttling; shared fixture
mutation; worker scheduling on Windows; stale accepted report reuse; required
checks on PRs that do not select Full verification.

**Local evidence:** Both throttled views pass. Independent reviews have no open
findings. Test inventory grew from 15,713 to 15,716 with no removals; Own-UML
assertions and parametrizations match Main. The same 76 TypeScript cases passed
with loadfile (622 s) and worksteal (132 s); these are single local runs, not a
Windows result. Full browser proof, Pages reuse, lint/type checks, architecture
comparison, builds and installed smoke tests passed. The complete local suite
passed: 15,655 passed, 61 skipped in 26:01 on four workers. The 59 Python-3.12
cases skipped on 3.11 also passed on 3.12; two Linux filesystem cases await CI.
CI timing and platform results remain pending.

**Merge policy:** Main now requires GitHub Actions `check` (app 15368) on an
up-to-date branch; existing rules and bypass restrictions were preserved.
