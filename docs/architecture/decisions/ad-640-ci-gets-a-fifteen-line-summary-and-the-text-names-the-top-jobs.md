# AD-640 CI gets a fifteen-line summary, and the text names the top jobs

**Status.** Proposed. Part of #880. It builds on AD-632 and closes #1348, #1351, #1353, #1354 and
#1355 (text part).

**Reason.** The second user test found a CI log of megabytes (a pipe gets JSON), a red CI whose
first line said "nothing differs", refusal lines with OS error codes and one generic fix, a next
step that named no job, and a finding without its usual fix.

**Decision.**
1. **The CI path is `--summary`.** It prints at most fifteen lines of text, also when stdout is a
   pipe or a file: the header with the exit code and its reason, the errors, the top jobs, five
   violations and a pointer to the full text. The rule of AD-632 stays: a pipe without a flag gets
   JSON, because tools read it. Rejected: text on stderr always (a tool that treats stderr as a
   failure would break, and the log would double) and `--format summary` (`--format` belongs to
   `report --output`). The README example for CI uses `--summary` and shows its log.
2. **An invalid baseline is a refusal of the baseline.** The header is `REFUSED -> exit 1
   (baseline FILE is not valid: why)`, with `Problem:` and `Fix:` first; the run is not compared and
   the text never says that nothing differs. The core still gives exit 1 (AD-546).
3. **The migration hint comes first.** A file of release 4.0.1 prints its hint before any other
   baseline line, and its entries are a count: all of them are new or stale by construction.
4. **`Next:` names up to three jobs, each with its count**, in order (violations, then the largest
   groups of gaps and open decisions). The rest is counted ("1 more below").
5. **A refusal has plain words and a fix of its own kind.** OS error codes (`[Errno 2]`,
   `(os error 2)`) and the raw OS text are replaced by words. A refused scan gets its fix from the
   part that the message names (`config:`, `root:`, `contract:`); each other kind has its own fix.
   "Development line" is now "not available in ArchKeel 5.0 yet; use release 4.0.1 for it".
6. **A finding with a usual cause names the fix once** (`module has no unique owner`: add the
   package to a component, a root package too). The table is `core_words.CAUSE_FIXES`; it is advice
   and decides nothing.

**Not done here.** The page (NEXT box, the same findings) is with the report author.
