# AD-650 The text says why a run of passing rules stays UNKNOWN and where a module went

**Status.** Proposed. Part of #880. Census classes K13 and K11 (text only; no verdict changes).

**Decision.**
1. **K13.** When no rule is UNKNOWN or FAIL and the run is UNKNOWN, the header says why: `all N
   rules pass; the run stays UNKNOWN because the contract draft has K open decisions` when each named
   part is a draft row (`decision.open`, `responsibility.missing`, `rationale.placeholder`,
   `rationale.repeated`, plus a drifted marked graph), else `... because K gaps are open`. The
   open decisions are listed below, grouped, as before.
2. **K11.** A gap `project_module_not_found: M` is its own group, "an imported module that has no
   file in the scan". Each line names the importer and `M`. The shell asks Git (`git check-ignore -v`
   for the files that `M` would have below each scan root) and, when a rule covers one, names it:
   `(no file; the ignore rule .gitignore:2 covers it, so it is probably generated)`. Without a rule
   it says `no file; it may be generated, or the import is wrong`. The group ends with the fix:
   generate or build the module before the scan, or leave out the files that import it.
3. The gap stays a gap. The scan does not guess the module and does not read the ignored file; Git
   only names the cause, and a failure of Git gives no hint, never a wrong one.

**Why sound.** Both changes are display. The core decides every verdict; a module that cannot be seen
holds the run exactly as before.
