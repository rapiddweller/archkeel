# AD-396 The native Python binding dump stops before import convergence

**Status.** Accepted. Part of #880. Stacked on #1091.
**Number.** The lead reserves 396 after the open-PR number check. PR #1098 uses 394.
This record takes the highest observed number plus two: AD-396.

**Reason.** The definition table still lacks binding proofs. Those proofs need the lexical
inventory, ordered lookups, namespace exposure checks and member-binding closure first.
The unused-binding collector needs the same own-body boundary. It has no import dependency.

**Measurement.** The selected Python spans contain 810 lines: 584 in `source.py`,
88 in `symbols.py`, and the 138-line `bindings.py` module. Some source helpers already have
restricted native forms in the import survey. This slice makes their ordered results directly
comparable at the pre-import boundary. It does not count these spans as deletable Python.
The PR lists modules, function spans and sizes. Use 810 as a lower bound, not a guessed total.

**Budget.** All 4,887 corpus files on 3.11–3.14: maximum 2,846,247 units, a 22.48-fold margin.
| Top five files (external paths relative to their corpus) | Units |
|---|---:|
| pydantic: `tests/benchmarks/corpus/google-genai/google/genai/types.py` | 2,846,247 |
| `src/archkeel/ir/facts_validation.py` | 2,520,034 |
| `src/archkeel/check/evaluation/boundary_types.py` | 2,163,788 |
| pydantic: `tests/test_json_schema.py` | 1,747,494 |
| `src/archkeel/analyzer/typescript/parse.py` | 1,484,327 |

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
5. Keep the parser budget at 2,000,000 units. Allow 64,000,000 for binding output and owner copies.
   Charge node loops, expression text bytes and copied owner-path bytes. Share owner paths
   through `Rc<str>` in both ownership walks. Charge two copies when a new path is built.
   Bound serialized output at 33,554,432 bytes, including JSON escapes and the final newline.
   Count records before retention and owner bytes before copying. Check the complete frame too.
   Exhaustion gives `binding work limit exceeded` or `binding output limit exceeded (33554432 bytes)`.
   Each refusal has incomplete scope and no partial data. New walks use heap stacks.
   Expression text keeps the existing depth bound and named text refusals.
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
and owner time/RSS scaling, exact loop costs, output bounds and empty-corpus failure.
Rust checks complete records, loop costs and byte counts. The PR records isolated faults and gates.
