# AD-380 The core decides the direction rule kinds

**Status.** Accepted. Epic #880, WP6 slice S5 (design WP6-0, section C; AD-363, AD-370, AD-372, AD-374, AD-378).

**Decision.**
1. The core decides the five direction kinds of the S5 row: `forbidden_dependency`, `allowed_dependency`, `sibling_isolation`, `layer_order` and `complete_requires`. The cycle part of the drop rule and `no_component_cycles` stay with S7; `interface_boundary` stays with S8.
2. `archkeel-model` holds one import matcher per kind (`model/src/direction.rs`): `forbidden` (`rule_support.py:98`, with the component pair of `ir/dependency.py:111`), `peers` (`rules.py:1387`) and `crossings` (`rules.py:1827`, `ir/model.py:318-385`). The evaluator writes a violation for each `Judged::Fail`; the scope proof counts each `Judged::Undecided` (`rules.py:856` `symbol_limits`). One matcher serves both, so they cannot drift.
3. Each kind states its doubt sources in `Scope::complete`; each match lists every kind:
   - the dynamic import reach of `rule_support.py:200`: the source side and the exact allowed sources of `forbidden_dependency`, a member of `sibling_isolation`, an owned module of `complete_requires`; a type-only limit misses a rule without type-only imports; a limit without its flag reaches the rule (it stops the reference engine). `layer_order` and `allowed_dependency` are not reached.
   - `Cause::Undecided`: an import whose names the reply does not prove.
   - the receipt (`rules.py:2685`): a module of the source side, a module of a member, the selected components of `layer_order` (`rules.py:1990`).
   - `Part::ContractSource`: a `layer_order` row and receipt cite the contract file (`check/observation.py:612`). The shell sends the path and bytes (`Settings::with_contract_source`); the model binds them to the parsed contract by the digest of the bytes.
   - `Part::ScanRoots`: the receipt of `complete_requires` needs the scan roots (`rules.py:2492`, `evaluate.py:1231`). The request has none, so `complete_requires` never passes.
   - `Part::ScopedRequires`: the host can accept a coverage gap for `complete_requires` with its dependency scope proof (`ir/decisions.py:1354`, `check/observation.py:990`), so such a gap is a part for that kind, not a fact.
4. An `allowed_dependency` rule is a permission declaration (`ir/decisions.py:760`): its outcome holds no `Decision`, the frame writes `DECLARATION`, and it holds back no PASS of the run (`check/run.py:76`). The harness accepts it with no row and no reason.
5. A reply with the symbol feature judges a symbol port of `requires` (`evaluate.py:1061` sets `dependency_symbols`); a reply without it leaves the import out, as the store-accepted profiles do, and the profile limit of AD-378 names the entry.
6. The violation rows are the rows of `rules.py:99`, `:1387`, `:1877` and `:2008`, sorted by id. A `layer_order` row cites the receipt `stable_id("RULE-EVALUATION", "root", rule)` and the file evidence of `ir/source_records.py:120`.

**Reason.** The direction kinds are the most used rules of the corpus (4 440 `forbidden_dependency` rules). Their FAIL rows and UNKNOWN causes are facts of the reply and the contract; only the receipt of `complete_requires` needs an input that the request does not carry.

**Amendment (2026-11-12, [AD-384](ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md)).** The request carries the scan roots, bound to the reply: `Part::ScanRoots` names only a request without roots, and the receipt of `complete_requires` can pass.

**Rejected.** A scan-root setting in the request: the cycle receipts of S7 need the same roots and the same physical domain check (`ir/coverage.py:123`), so S7 adds it for both. A matcher per consumer: the undecided count and the violations would drift. A bare `Verdict::Declaration`: the report crate already keeps a declaration outside `Decision`.

**Stricter than Python (all named).** `complete_requires` that Python passes: 81 rules name the scan roots. A profile limit of AD-378 (a symbol selector, an interface boundary, a symbol port) in the same contract: 6 `forbidden_dependency` and 5 `sibling_isolation` rules that Python passes. A rule of a mounted tree keeps the `TreeScope` check of AD-379 before PASS. A reply that the store refuses and a baseline: named as before.

**Limit.** Parity holds only for replies that the store accepts (TypeScript, Rust). A `requires` symbol port without the symbol feature is left out: a profile that judges it without the feature (none is store-accepted) would show more rows. The symbol feature is the one feature of the reply; a registered feature set that holds it and is not the full set of `evaluate.py:1061` does not exist today. The core does not re-read the contract file after the shell read it. Inside rules stay named gaps (AD-379).

**Corpus (635 cases, after AD-379).** Both agree: `forbidden_dependency` 54 PASS, 41 FAIL, 37 UNKNOWN; `sibling_isolation` 55, 1, 19; `layer_order` 2, 3, 1; `complete_requires` 0, 36, 15; `allowed_dependency` 1 DECLARATION. Each other rule is named (a mount scope that the core does not clip, an inside rule, a refused reply, a baseline, the parts above); the 1 507 other `allowed_dependency` rules are DECLARATION in Python and named in the core. Core decides where Python differs: 0. Core run status PASS or FAIL where Python differs: 0 (PASS 2 and FAIL 107 agree). The 28 cases `s5/*` give per kind a PASS, a FAIL with several rows and one doubt per case (type-only edges, a re-export, an external and a builtin target, a module in two selectors, a planned-only selector, an exact source that selects nothing, self edges, a symbol position, three tampered Rust replies with a dynamic import limit).

**Tests.** `native/eval/src/direction_tests.rs`, `direction_scope_tests.rs`, `receipt_tests.rs`; `native/core/src/dual_run_tests.rs` (`a_declaration_has_its_word_and_a_layer_row_cites_the_contract_file`), `status_tests.rs`; the attempts 18 to 20 of `native/model-barrier`; `tests/test_native_core.py` (`test_the_direction_kinds_give_the_verdict_of_python_or_an_exact_name_on_every_case`).
