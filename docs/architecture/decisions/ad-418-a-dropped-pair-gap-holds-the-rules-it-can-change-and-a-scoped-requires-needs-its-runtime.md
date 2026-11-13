# AD-418 A dropped pair gap holds the rules it can change, and a scoped requires needs its runtime

**Status.** Accepted. Part of #880, goal M2: the core decides the self-contract of `native/`. It changes point 4 of [AD-384](ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md) and `Part::ScopedRequires` of [AD-380](ad-380-the-core-decides-the-direction-rule-kinds.md).

**Measurement.** On the self-check of `native/` the core refused 24 of 43 rules: 23 with `Part::AllowedPairGap`, 1 with `Part::ScopedRequires`. Python gives UNKNOWN for all 24.

**Decision.**
1. Dropped gap. The drop rule of AD-384 point 4 still decides which pair gaps it drops. The model keeps each dropped gap (`Pairs::dropped`). A dropped gap holds a rule when it can change the reading of the rule (`model/src/dropped_gaps.rs`). The rule is then UNKNOWN with `Cause::AllowedPairGaps`, which names the gaps. `Part::AllowedPairGap` is removed.

| Kind | A dropped gap `a -> b` holds the rule when | Proof |
|---|---|---|
| `no_component_cycles` | an end is not a module of the reply | The drop rule keeps each gap whose target reaches its source in the known imports plus every pair gap, at each active level. The cycle rows read the same imports. One component adds no component edge. |
| `complete_requires` | an end is not a module of the reply | A dropped edge lies in one component, which `crossings` skips, or follows a `requires` entry without `through`, which `assessment` judges PASS. So it adds no FAIL and no undecided position. |
| each other kind | the reading of AD-384 point 5 holds | The drop rule reads selector texts, not the sides of a rule (review B1 of #1084). A whole-component side or an external re-export can still read the edge. |

   An end that is not a module of the reply can have imports that no reach saw, so such a gap holds every rule.
2. Run. A dropped gap holds the run when it holds a rule of the contract. A dropped gap that holds no rule changes no verdict. Then the run is as in the host, which forgets the gap.
3. Scoped requires. The host accepts a dependency scope proof only from the runtime `python` (`ir/decisions.py` `_native_scope_runtime_valid`). The facts crate names that runtime (`Runtime::carries_scope_proof`); the model names no language. For any other runtime, a coverage gap or a kept pair gap of `complete_requires` is a fact: UNKNOWN with the gap, as in the host. For that runtime the rule stays `Part::ScopedRequires`: the core does not replay the proof.
4. The core still refuses for a reply of the runtime that can carry the proof, for a contract with mounts that the model does not read (`Part::MountedTree`) and for each other part of AD-378 to AD-385. A tree keeps each pair gap as a cause (AD-385).

**Direction.** For a dropped gap the core is equal to Python or stricter. Where a dropped gap holds a rule, Python forgets the gap and can give PASS; the core gives UNKNOWN. No corpus case has this today. Where no gap holds a rule, the core gives the verdict of AD-384 point 5. Over a Python UNKNOWN for a kept gap, that is a PASS that the frame lists in `beyond`.

**Self-check (`native/`, first measurement, 43 rules).** Before: 19 rules decided (18 UNKNOWN, 1 FAIL), 24 refused. After: 43 decided, 0 refused: 1 FAIL, 19 UNKNOWN, 23 PASS beyond Python (22 `forbidden_dependency` rules and `complete_assignment`). No kept gap can change these 23. The run stays FAIL and names each kept gap (39 at the measurement). After #1107 the contract has 79 rules: 79 decided, 1 FAIL, 19 UNKNOWN, 59 PASS beyond Python (58 `forbidden_dependency`, `complete_assignment`), 112 kept gaps.

**Corpus (655 cases).** 16 rules change from a refusal to a decision: 15 `complete_requires` UNKNOWN, equal to Python, and the `complete_assignment` rule of `rust/native`, PASS beyond Python. 64 `ScopedRequires` refusals stay. Each is a reply of the runtime that can carry the proof, and Python passes 15 of them. No decided verdict changes.

**Rejected.**
- Drop the gap as the host does. The drop rule does not see a whole-component side, so this can give a false PASS. A planted test shows it.
- Hold every rule for any dropped gap. This is sound, but it loses each verdict that the gap cannot change.
- Replay the dependency scope proof in the core. It needs the receipt bindings of the host, and no reply of a Rust collector carries the proof.

**Limit.**
- The proof reads the drop rule of the core (`pair_gaps.rs`), not the drop rule of the host. Its cycle part and the cycle rows read the same imports of the model.
- A PASS over a gap needs a gap for each visible candidate of a called method name (`rust/src/impl_edges.rs`). A test pins two candidates (review B1 of #1121).
- A candidate in another crate that the caller names by a renamed Cargo dependency is a gap too: the manifest reader keeps the package of the dependency. A test pins it (review F3 of #1121).
- A cross-crate candidate follows the transitive Cargo closure of the caller (`impl_edges.rs` `depends`, review B2 of #1121). Tests pin a value that a dependency returns, a re-export, a type alias, `Deref` and a closure parameter (`rust/src/transitive_edges_tests.rs`). The pin of `native/` gets one gap: `core.engine -> facts.envelope.build`.
- Two forms stay open, in one crate as across crates, and a test pins each: a trait method (`impl Trait`, `Box<dyn Trait>`, #1004) and a method in the file of its type, called on a value that the caller does not name. The scan lists neither as a candidate. On `native/` a value can reach `core` from a collector crate only through `collect`. The row `NATIVE-NO-CORE-TO-TYPESCRIPT` holds because a test pins, by value, the import records of the reply from `collect` to each collector crate; an alias or a renamed dependency is a new record and fails the test (review B3 of #1121).
- A PASS beyond Python is only as strong as the edge model. The open false-PASS classes #1004 (a trait `impl` in a third module) and #1020 (an item that a macro makes) give no edge and no gap, so a Python UNKNOWN for a kept gap hid them and a core PASS does not. This is a named limit; no test checks it on other trees.

**Tests.** `native/model/src/dropped_gaps_tests.rs`; `native/rust/src/impl_edges_tests.rs` (B1, F3); `native/eval/src/dropped_gap_tests.rs`, `scoped_requires_tests.rs`, `drop_rule_tests.rs`, `gap_scope_tests.rs`, `direction_scope_tests.rs`; `tests/test_native_self_core_rows.py`; `tests/test_native_core.py` (`BEYOND_CASES`).
