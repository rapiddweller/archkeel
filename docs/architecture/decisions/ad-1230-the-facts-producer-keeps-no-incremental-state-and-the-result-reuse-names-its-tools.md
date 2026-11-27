# AD-1230: The facts producer keeps no incremental state, and the result reuse names its tools

Status: accepted. Amends AD-1047 and AD-1061. Closes #2140. Point 2 (the reuse inputs of the saved base result) is superseded by [AD-1260](ad-1260-the-self-check-gate-checks-one-run-and-compares-nothing.md): there is no saved base result.

## Why

The PR base job hit its 15-minute limit when the saved self-check result of the base commit was missing. It then
scans the PR tree (about 6 minutes) and the base commit (358 s). Of 352 s of core time, 62 s is the collector; about
290 s is the compiler facts: one `cargo check` of the workspace for each of 9 configurations, cold in each job.

## Decision

1. The sealed Cargo run passes `--config build.incremental=false`. A one-shot check gains nothing from incremental
   state. Measured on one machine (macOS, 10 cores), cold cache: 287 s before, 198 s after (31 % less); the work
   directory of one configuration shrinks from 815 MB to 278 MB. The report is identical: status, rules,
   violations, premises, scope, measures, 12929 gap records and the holds of each rule are equal; only the line
   numbers of the edge evidence in the changed file differ.
2. The saved result of an earlier main commit stands for the base only when no input differs (AD-1061). The inputs
   named `tools/self_check_*.py` were a glob. They are now `self_check_diff.py`, `self_check_contract.py` and
   `self_check_gate.py`: the code that condenses and normalizes the result. `self_check_summary.py` and
   `self_check_shell.py` read a result and print, so a change there no longer voids the saved result.
3. No scanned input is dropped: `native`, `tools/rustc-facts`, `src`, the lock files, the Makefile and the condensing code
   still decide.

## Not done yet

- A CI cache of the facts work directory was measured and rejected: 12 GB for 9 configurations against a 10 GB limit
  of the repository; the warm run is only 31 % faster, because a fresh checkout has new file times.
- Main CI loses the saved result of a commit when its run is replaced in the queue (8 of the last 30 runs). The gate
  then computes the base. Saving the result in a separate job is a later step.
