# AD-392 The native Python binding dump stops before import convergence

**Status.** Accepted. Part of #880. Stacked on #1091.

**Number.** Main ends at AD-387. Open PRs include AD-388, AD-389 and AD-390.
The final number check takes the highest observed number plus two: AD-392.

**Reason.** The definition table still lacks binding proofs. Those proofs need the lexical
inventory, ordered lookups, namespace exposure checks and member-binding closure first.
The unused-binding collector needs the same own-body boundary. It has no import dependency.

**Measurement.** The selected Python spans contain 810 lines: 584 in `source.py`,
88 in `symbols.py`, and the 138-line `bindings.py` module. Some source helpers already have
restricted native forms in the import survey. This slice makes their ordered results directly
comparable at the pre-import boundary. It does not count these spans as deletable Python.
The PR lists all analyzer modules and their measured sizes. There is no prior exact ledger
of partly ported lines. Use 810 as a conservative lower bound, not a guessed cumulative total.

**Decision.**
1. Add `--dump-bindings <minor> <root>` under the existing `dump` feature. Each input line names
   one snapshot file. Each output line holds its binding inputs, unused-binding records and
   cited evidence, or one named gap with `full_scope: false` and no partial data.
2. Compare against the unchanged Python functions on a fresh `ParsedModule`, before import
   convergence. Its alias map and provider proof sets are empty. The dump does not assert
   any post-import binding, class kind, runtime ownership or stable member proof.
3. Keep the exact Python traversal orders. The whole walk is breadth first. The own-body and
   evaluated-module walks are depth first. The latter excludes comprehension target binders.
   Nested functions keep their enclosing class for the unused-parameter heuristic.
4. Keep member-binding closure as a work list. Assignment aliases give edges in both directions.
   Containment gives a directed edge. A namespace expands once. Explicit local references
   do not give alias edges. The dump checks default and explicit proof inputs.
5. Charge the additional walks, text bytes and closure edges against the existing work budget.
   Exhaustion gives `binding work limit exceeded`, never a partial inventory. New walks use
   heap stacks. Expression text uses the existing depth bound and named text refusals.
6. Assign the binding modules to `py-symbols`. Put the bounded scan below its consumers, as
   `symbols::scan` does. Keep shared definition locations and import names in `py-module`.
   Share the namespace name tables with the survey. Add no clone baseline entry.
7. Keep the production reply unchanged. The new complete unused-binding records are available
   for later record assembly. The symbol section is still incomplete. The host and store
   still refuse the native Python reply. No Python analyzer behavior changes.

**Stricter.** The new work bound can refuse an otherwise readable file. Existing compiler,
expression-depth, surrogate and format-spec refusals remain named gaps. Shared parse refusals
and native-only refusals have separate counts in the parity evidence.

**Rejected.** (a) Guess stable bindings from an unprocessed alias map: this can give a false
PASS. (b) Declare a partial symbol section in the reply. (c) Repeat the import-name or location
helpers. (d) Revisit every binding for each namespace read: precompute the blocked-name set.

**Limit.** This is the pre-import boundary, not the remaining symbol-proof port. The class
statement dump uses the default admission inputs. Provider-proven and inert-value admission
remain outside this dump. No speed improvement or Python deletion is claimed.

**Tests.** `test_collector_native_python_bindings.py` compares fixture and corpus files,
160 generated probes per Python minor and direct edge probes. It checks named work exhaustion
and scaling of both flat functions and namespace reads. The Rust binding self-check checks
complete records and the work count. The PR records isolated fault injections and all gates.
