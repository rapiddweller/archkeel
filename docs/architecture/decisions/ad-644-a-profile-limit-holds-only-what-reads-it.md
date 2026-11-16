# AD-644 A profile limit holds only what reads it

**Status.** Proposed. Part of #880. It amends item 4 of AD-500 and the profile limit item of AD-378 and AD-385 (`limits.rs`, `proof.rs`). It applies the read-set rule of AD-564 and AD-634 to the profile limits.

**Reason.** A profile limit was a coverage failure of the run: no rule of the run passed. The Python collector examines no construct (`native/python/src/reply.rs`), so one `forbidden_construct` rule held every rule of the run. The same was true for one rule of a kind that no profile decides (`symbol_placement`) and for one measurement budget that no profile measures (`private_crossings`). On three real Python projects (DATAMIMIC CE and two private projects) this held 267, 457 and 20 rules, also each `root_layout`, `complete_assignment` and `external_dependency_scope` rule. A construct cannot change an import edge, a file or an owner, so these rules can decide. The reference engine (`profile_failures`) makes each limit a failure of the run. That is a choice of the reference engine. Soundness does not need it.

**Decision.**
1. `limits::rule_limit` gives the limit that holds one rule: the limit of the rule itself (`own_limit`), else the limit of the first symbol selector that the rule reads (`symbol_reader`, AD-500). `Scope::complete` holds the rule with it (`limits::hold_rule`), after the state of the scope and before the gaps.
2. `limits::run_limits` gives the limits that no rule reads: a declaration (`context_roots`, `facade_budgets`, `coupling_budgets`, a measurement budget that no profile measures) and a symbol entry of a component. `Scope::run` holds the run with them (`limits::hold_run`). They hold no rule.
3. A profile limit is no longer part of the one scope state of a model (`proof::state`). This is also true for the limits of a mount: the limit of a mount rule holds that rule.
4. A limit of every store-accepted profile is a fact (`Cause::ProfileLimit`), a limit of some profiles is a named part (`Part::ProfileLimit`), as before. The subject of a construct limit names what the collector does not examine: `NO-GETATTR: the collector examines no getattr`.
5. The run status does not change: `run_complete` needs a PASS of each rule, so a held rule keeps the run UNKNOWN. A hygiene row (`hygiene:budget`) still names each measurement budget.

6. The scope line of coverage gaps counts the gaps that the report lists. `Incomplete::CoverageGaps` carries both numbers of the one class of each gap (`gap_class::classes`): each reported gap, and the gaps that leave the whole scope unknown. When they differ, the line names both: `the collector reports 4 coverage gaps; 3 of them leave the whole scope unknown` (the fourth gap states its effect, AD-564). Before, the line said `reports 3 coverage gaps` beside a report that listed 4.

**Why it is sound, by rule kind.** A limit makes one part of the facts unknown. A PASS is sound when each part that the rule reads is known. So a limit must hold each rule that reads its part, and only those. `limits::reads` states what each rule kind reads. Its match has no catch-all arm, so a new kind does not compile until it states what it reads.

| Limit | Part that it makes unknown | Reader (code) | Rules that it holds |
|---|---|---|---|
| unexamined construct, construct selector | the construct sites of the named constructs | `construct_match::matches` and `receipt`, only from `constructs::check` | the `forbidden_construct` rule itself |
| kind that no profile decides (`UNDECIDED_KINDS`) | the facts of that kind | none: `evaluate` answers `Unsupported::Rule` for the kind | the rule itself |
| no type shapes (AD-550) | the shapes of written types | `boundary_positions::read` | the `boundary_types` rule itself |
| `interface_boundary` not stated | the publication surface | `interface::receipt` | the `interface_boundary` rule itself |
| symbol selector not stated (`symbol_reader`) | the symbol facts | `direction::forbidden`, `direction::crossings`, `interface::assess` (AD-500) | the `target_symbol` rule, each `complete_requires` rule with a symbol port, each `interface_boundary` rule |
| declarations, measurement budget | a measure | no rule reads it: its only reader is `limits.rs` | the run (and the UML target row, which needs the run) |
| symbol entry of a component | the symbol facts of that entry | the readers in the symbol row above | those readers, and the run |

The other facts stay complete: the Python collector writes the import edges, the files and the owners from the source, not from the construct, kind or budget statements. The construct inventory is not read by an edge, layout, assignment, external or cycle rule. A seen violation is still FAIL, because `decide` gives FAIL before the scope proof.

**Measured** (main `8795c8c85` before, this change after; rules PASS/FAIL/UNKNOWN):

| Project | Before | After | What still holds the other rules |
|---|---|---|---|
| DATAMIMIC CE (276 rules) | 0/0/276 | 173/0/103 | 6 construct rules (own limit), collector gaps (AD-634); a `private_crossings` budget holds the run |
| private project A (479 rules) | 0/0/479 | 256/0/223 | 2 construct rules (own limit), 78 collector gaps |
| private project B (22 rules) | 0/1/21 | 14/1/7 | 5 construct rules (own limit), `interface_boundary` (unproven route), `complete_requires` (an owner); the FAIL stays |
| self system run | PASS | PASS | |

No FAIL appears. Each new PASS is a `root_layout`, `complete_assignment`, `external_dependency_scope`, `complete_external_scope` or `no_component_cycles` rule. In `fixtures/`, `F-architecture` goes from 0 to 25 PASS and `F-architecture-tests` from 0 to 5 PASS.

**Rejected.**
- Keep the limits of the run as in the reference engine: it is not a soundness need, and it hides each rule that the scan can decide.
- Hold the run only for a declaration and decide each declaration later: no evaluator reads a declaration today, so the run stays UNKNOWN until one does.

**Tests.** `profile_limit_tests.rs` (eval: each limit holds only its rule, a declaration holds the run and no rule, a seen violation beside a limit stays FAIL), `tree_scope_tests.rs` (a mount limit), `test_cli_python_profile_limits.py` (CLI plants: a construct rule, a seen violation beside it, a `symbol_placement` rule and a `private_crossings` budget, with the truth of each plant by Python), `test_collector_native_rust.py` (a construct rule and a `symbol_placement` rule beside the crate rules).
