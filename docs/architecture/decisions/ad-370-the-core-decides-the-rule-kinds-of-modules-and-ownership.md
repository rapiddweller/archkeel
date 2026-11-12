# AD-370 The core decides the rule kinds of modules and ownership

**Status.** Accepted. Epic #880, WP6 slice S1 (design WP6-0, section C; AD-359, AD-363).

**Decision.**
1. `archkeel-model` holds the modules of the reply in reply order, the packages in name order and
   the one owner of each module. A module has an owner only when exactly one component claims
   it (`sole`): a nested package of two components and a module that two components name both
   leave it without an owner. It also holds `Incomplete`: what the reply itself proves not seen
   (no selected file, or a coverage gap that no contract can drop).
2. A new library crate `archkeel-eval` decides each rule. An `Outcome` holds a `Decision`, never
   a bare `Verdict`. Slice S1 decides `complete_assignment` and `root_layout`, the kinds that read
   only modules, packages and owners. The order is the order of Python `_rule_status`:
   - a violation gives FAIL; a violation is a fact also in an incomplete scope;
   - an `Incomplete` gives UNKNOWN (`Reason::Incomplete`);
   - a rule that selects no module has no evaluator receipt and gives UNKNOWN
     (`Reason::NoSubjects`);
   - else PASS needs `Scope::complete`. Until slice S4 that is `Unsupported::ScopeProof`, so the
     rule is a named gap in `unsupported.rules`, never PASS.
3. `eval` uses `model`, `contract` and `facts` (only `identity::stable_id`, for the record ids of
   Python). `core` uses `eval`. Each rule kind that no slice ports answers
   `Unsupported::Rule(kind)`.
4. The core has a `Rules` request (`core/src/rules.rs`). The dual-run frame has the status of
   each decided rule in `rules`, and the `violations` rows of the decided kinds in `sections`.
   A rule of a decided kind without a model names the missing input.
5. The rows of `modules` and `packages` hold fan-in, fan-out and the rank; the model of S1 is
   their input. Slice S3 writes them ([AD-374](ad-374-the-core-ranks-the-edges-and-derives-the-modules-packages-and-cycles.md)).
6. A gap with a `source_module` and a different `module` is not an `Incomplete`:
   `drop_allowed_pair_gaps` can drop it for some contracts. The check names no language, so it
   treats such a gap as not proven for every profile.

**Reason.** A false PASS is the largest risk of the Rust evaluator (AD-363). FAIL and UNKNOWN from
facts that the model sees are sound before the scope proof exists. The Python verdict of these
kinds also depends on facts that S1 does not see (the subject check of every rule, unknown
imports, profile limits): those are the scope proof of S4, so S1 does not guess them.

**Python replaced.** `ir/ownership.py` `sole`, `ir/model.py` `component_for` and
`package_owners`, `check/evaluation/rules.py` `_assignment_violations`, `_root_layout_violations`
and `_modules_for_rule_source`, and the S1 part of `ir/decisions.py` `_rule_status`. The PR lists
each with its line. They go when the store path is the only path (design WP6-0, cut rule).

**Differences to Python (all equal or stricter).**
- A rule that Python passes is a named gap (`the scope proof: slice S4 ports it`): 62
  `complete_assignment` and 8 `root_layout` rules of the corpus.
- A rule that Python gives UNKNOWN for a cause that S1 does not see is the same named gap: 19
  `complete_assignment` and 1 `root_layout` rules (Rust probes with a hidden edge or crate, the
  subject check of another rule).
- No rule is decided differently (0 unnamed differences, 543 cases); 16 baseline rules are named.

**Rejected.**
- PASS when the reply has no gap. The coverage of Python also fails on the subject check of
  every rule, on unknown imports and on profile limits; a PASS there is the false PASS of AD-363.
- Rows of `modules` and `packages` without fan-in, fan-out and rank. The harness compares whole
  rows, and a partial row is never equal.
- The rule evaluation inside `model`. The model derives; the evaluator decides (AD-359).

**Limit.** The store refuses the Python and Dart replies, and the core refuses a contract with
inside contracts, so these cases name their missing input. These two classes hold 17 rules that
Python decides FAIL (11 behind inside contracts, 6 behind a refused reply), which the core cannot
read yet. A request with a `baseline` is refused by name (`Unsupported::Baseline`) until a slice
reads it. A layout child without a module record is UNKNOWN (`Reason::UncitedChild`), where
Python stops with `KeyError`. `make dual-run` with
`--sections violations --families complete_assignment,root_layout` compares 4 FAIL and 57 UNKNOWN
`complete_assignment` rules and 4 FAIL and 4 UNKNOWN `root_layout` rules as equal; the 13 cases
`s1/*` of `tests/dual_run/cases.json` add the FAIL and UNKNOWN cases of AD-360 point 10.

**Tests.** `native/model/src/model_tests.rs`, `native/eval/src/eval_tests.rs`,
`native/core/src/engine_tests.rs` and `dual_run_tests.rs`; `tests/test_native_core.py`
(`test_the_s1_kinds_equal_python_or_name_the_scope_proof`,
`test_the_model_the_evaluator_and_the_core_name_no_language`).
