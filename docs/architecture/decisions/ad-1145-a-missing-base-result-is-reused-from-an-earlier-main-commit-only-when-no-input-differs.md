# AD-1145 A missing base result is reused from an earlier main commit only when no input differs

**Status.** Accepted. Amends [AD-1061](ad-1061-the-self-check-is-compared-with-its-base-commit-beside-the-pins.md), point 2 and its Limit. Superseded by [AD-1260](ad-1260-the-self-check-gate-checks-one-run-and-compares-nothing.md): the self-check compares nothing.

**Reason.** The job "PR base checks" has a 15-minute limit. Issue #2077 measured 40 PR gate runs: 5 of 27 observed restores were misses, and 4 of those 5 jobs were cancelled. 0 of 22 hits were cancelled. A miss happens when main CI has not saved the entry of the base commit before the PR gate starts. The gate then scans the base commit in a worktree. The log did not time that scan.

**Decision.**
1. **Measure.** The gate prints `base result: scan took N s` after each computed base. It prints the hit, miss and reuse lines with a flush, so a cancelled job still shows them.
2. **Restore keys.** The PR gate lists the 8 nearest first-parent commits before the base commit as restore keys, nearest first, then the v1 key. The cache action allows 10 keys in all, with the key of the base commit.
3. **Reuse.** The gate uses an entry of an earlier commit E as the base result of the merge base B only when all of these hold: the entry is a complete `selfcheck-v2` result; `E` is a full 40-hex sha; the entry's `tree` equals `git rev-parse E:native`; and `git diff --quiet E B -- INPUTS` finds no change. `INPUTS` is one list in `tools/self_check_gate.py`: `native`, `tools/rustc-facts`, `src`, `pyproject.toml`, `uv.lock`, `Makefile` and `tools/self_check_*.py`. The scan also reads the whole repository for Cargo settings, so a change anywhere that touches a `.cargo` path, a link, a path deeper than 100 parts, or a tree of more than 250 000 files blocks the reuse (found by Codex in review). The core also reads the documents that the contract cites (provenance, AD-466: the marked graph of `native.md`, each cited decision). The gate derives them from the cached result, not from a list: the files it bound (`contract_files`) and every string of those contracts that the core could read as a path (the rule of `normal()` in `provenance.rs`: no backslash, colon, NUL, empty, `.` or `..` part), also a name with a space or without a slash. A file that differs, or that appears or disappears, between the two commits blocks the reuse (found by the verification run). The reused entry gets `sha` of B and `reused_from` E. The gate prints the reuse.
4. **Else compute.** Any other case is a miss as before: the gate computes the base in a worktree. It never reuses an entry of a commit whose inputs differ, because that would hide growth.
5. **No longer timeout.** The limit stays at 15 minutes. A longer limit needs a measured scan time first (point 1).

**Rejected.** Reuse of any earlier entry: a changed `native/` would give a false green. A longer timeout without a measured cause. A new fingerprint file: the git trees of `INPUTS` already name every input, so there is one source.

**Limit.** `INPUTS` lists what the result depends on today. A new input (for example a new tool that changes the report) must join the list. The test `tests/test_self_check_gate.py` fails when an input in the list stops forcing a recompute, but it cannot find an input that is missing from the list.

**Tests.** `tests/test_self_check_gate.py`: a hit, a reuse for each unrelated change, a recompute for each input in the list, an entry with a wrong tree or no known commit, and growth found against a reused entry.
