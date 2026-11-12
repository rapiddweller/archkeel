# AD-390 A user run takes its verdict from the core when the core decides every rule

**Status.** Accepted. Epic #880, lead decisions L-63, L-35c, L-70 and L-71. It follows AD-388.

**Decision.**
1. Request kind. `archkeel-core check` reads protocol `archkeel-core-check-1`: the root contract
   (path and bytes), the inside contracts that the core asks for (AD-379), the collector reply,
   the scan roots, the namespace and a baseline flag. The core reads no file, so the shell sends
   the bytes that it read. `native/core/src/check.rs` decodes it and calls `dual_run::run`, the
   one engine path of both request kinds; only the envelope and the trust function differ.
2. Trust root of stage 1: the shell. The request has no producer, pin, profile, `Settings` or
   standard library field, and an unknown field refuses it (exit 2). The core reads the profile
   from the reply and takes the pinned standard library of that profile. The reply passes through
   the shell, so its `code_digest` is public text that a caller can write; it is no proof. The
   core reaches trust only in `check::stage_one_shell_trust`: the reply must name the collector
   of its profile and the code digest of this core build. This catches a stale build, not a
   forgery. The shell is the trust root: with the switch, it starts each bundled collector and
   the core only after the file has the digest of its `.sha256` file (`observe.verified_binary`,
   AD-352); a missing or stale digest is an error (exit 2). It sends no reply of a configured
   `collector_argv`, and it refuses `ARCHKEEL_NATIVE_STORE`. The repository and the environment
   cannot name another `_native` directory. Stage 1 accepts this root for one reason only: Python
   decides the same run from the same reply, and any difference is an error, so the verdict of
   the user is never weaker than the Python verdict of today.
3. Switch. `archkeel report --native-core` or `ARCHKEEL_NATIVE_CORE=1`; off by default. Another
   value of the variable is an error.
4. Stage 1 rule. The Python engine still runs. When the frame names no part and the core exits
   0, the run status and each rule status that the user gets are those of the core, and each must
   equal the Python status (FAIL also by count). A difference is an error with exit 2 and no
   artifact. A PASS of a rule that the core names in `beyond` and Python gives UNKNOWN is shown as
   such (AD-384). When the core names any part, Python exits 2, the run has more or fewer than
   one reply, or the collector is configured, the result is the Python result with one note that
   names each reason. No rule mixes the two engines.
5. Frame reader (`cli/core_frame.py`). Typed values and enums. It refuses a missing or unknown
   field, an unknown word, a status without its row, trailing text, a second frame, an exit code
   that does not fit the frame, a run PASS with a row that is not PASS or a declaration, and a run
   PASS with zero rules. Both engines give PASS for a contract without rules; #1096 decides one
   policy, and the reader keeps the refusal until then.

**Stages.**
- Stage 2: for a run that the core decides, `run_report` no longer computes the verdict. Entry,
  all of them: the core runs the native collectors itself in its own process, so that no reply
  passes through a caller (#1095); every case of the corpus run with the switch, at least 600,
  gives 0 differences in two runs on `main`; the core writes the evidence rows of the report.
  Without the first condition, stage 2 must not start.
- Stage 3: the switch is on by default and a platform wheel carries `archkeel-core`. Entry: stage
  2 holds for one release, and no fall-back reason is left for a supported profile.
- Next step, done by AD-399: `archkeel check`. `run_check` sets `rule_assessments` with the call of
  `inspect_observation` (`check/run.py:358-375`), so `check` and `report` share the rule rows. The
  switch goes on `check`; the core takes the candidate reply and the contract read from Git at
  the baseline; the shell compares the verdict, the rows and the exit code.

**Deletable Python, by imports** (`ir`+`check`: 127 modules, 63 969 lines). Stage 1 and stage 2
delete nothing: every fall-back run still needs the whole engine. Without the three verdict entry
points, 124 modules (61 462 lines) stay reachable from `render`, `analyzer`, `studio` and the
other commands. At stage 3 only `check/report.py` (1 418), `check/validation.py` (1 330) and
`check/run.py` (387) lose all other importers.

**Reason.** 149 merged PRs gave no user verdict from the core. A user run must take its verdict
from the core before `ir` and `check` can go, and a silent difference must not reach a user.

**Rejected.** The digest as a proof of the producer. A per-rule mix of two verdicts. A fallback
to Python for a missing or changed binary. A file read by the core (the pin of AD-382 stays).
`archkeel check` in this slice: `run_check` gives no rule rows to compare yet.

**Limit.** A caller with write access to the install can write any reply. In stage 1 the shown
evidence (`architecture.json`, HTML) is the Python evidence. The fall-back note classifies a
reason by its first words; it decides nothing.

**Tests.** `tests/test_cli_native_core.py`, `tests/test_cli_native_core_frame.py`,
`native/core/src/check_tests.rs`, `tests/test_native_core.py`, `tests/test_dual_run_shell.py`.
