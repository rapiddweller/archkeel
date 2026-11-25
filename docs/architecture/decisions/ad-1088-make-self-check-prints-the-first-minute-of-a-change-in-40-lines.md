# AD-1088 `make self-check` prints the first minute of a change in 40 lines

**Status.** Accepted. Issue #1988. It amends [AD-1064](ad-1064-the-pin-files-are-deleted-and-the-base-comparison-is-the-only-self-check-gate.md) (the tools of the gate) and [AD-314](ad-314-source-files-have-at-most-500-lines-and-legacy-files-only-shrink.md) (where the size rule lives).

**Reason.** An agent that changes ArchKeel found the verdicts, the growth against the base, the UNKNOWN causes, the file sizes and the import hotspots in four places. Size and hotspots were found by hand (#954, #357, #1723 to #1725). The builders of the tool did not see what the tool knows.

**Decision.**
1. **One command.** `make self-check` runs `make -k self-validate` (all three checks report, also after a failure) with its output in `test-artifacts/selfcheck/self-validate.log`. Then `tools/self_check_summary.py` prints at most 40 lines. The exit code is the exit code of `make self-validate`: only the base comparison of AD-1064 can fail it.
2. **No second checker run.** `self-validate-native` and `self-validate-shell` call `archkeel report --json --topology`. The condensed result equals the result of `archkeel validate --json` (`tools/self_check_diff.py same`). The system target calls `archkeel report --text --output <file> --format json` and keeps its text. The summary reads these files.
3. **Groups.** Each group ends with one `next:` line.
   - Verdict, with the exit code of the status, for native, shell and system.
   - Growth against the base commit in words: new items and gone gaps. The gate keeps the base that it compared in `test-artifacts/selfcheck/compared-base.json`.
   - New violations, with the first `file:line` of the evidence. The base passed its gate, so each violation is new.
   - UNKNOWN causes: the collection gaps by cause, the largest five, with the first `file:line`.
   - Size: files over 500 lines that `tests/file_size_baseline.json` does not hold, the count of files at 450 to 500 lines, and the names of the files at exactly 500 lines (30 at most).
   - Hotspots: the five scanned modules with the most importers and the five with the most imports, from the import edges of the topology.
   - Cycles: the cycles that the rules of kind `no_component_cycles` found, and the cycle rules that wait.
4. **Measured, not decided.** Size, hotspots and cycles carry the word `measured` or name the rule. They never change the exit code. No rule kind for size or fan-in exists (`docs/rules.md`: type fan-in is a review candidate).
5. **One size rule.** `tools/file_size.py` holds which files the limit covers, the limit and the line count. The hygiene test and the summary import it.
6. **Caps.** Each group has a fixed cap, so the text has 40 lines at most for any input.

**Rejected.**
- A new fact for line counts in the snapshot or the core. AD-314 owns the rule, and a second source would drift. #1984 owns the snapshot.
- A second checker run for the topology. It costs a full scan.
- A fan-in rule or a score. Measures are not verdicts.
- A component cycle search in the summary. The rule of the core decides cycles.

**Limit.**
- The ranking of UNKNOWN causes counts gaps. `explain.holds` keeps 500 gaps, so the exact count of rules that a cause holds is not in the result.
- Fan-in and fan-out count scanned import edges only. The core measures of a module also count macro bodies, so the numbers differ.
- The shell gate shows no ratchet words; its failures are in the log.
- The system result has no exit code. The summary maps its status with `EXIT_TABLE`.

**Tests.** `tests/test_self_check_summary.py` (40 lines for the largest input, the counts equal the result, size, ratchet words), `tests/test_cli_shell_self_check.py::test_the_summary_lists_a_planted_import_with_its_place` (a real result), `tests/test_make_self_check.py`, `tests/test_repository_hygiene.py`.
