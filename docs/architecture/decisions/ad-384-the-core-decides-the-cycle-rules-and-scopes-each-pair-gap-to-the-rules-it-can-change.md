# AD-384 The core decides the cycle rules and scopes each pair gap to the rules it can change

**Status.** Accepted. Epic #880, WP6 slice S7 (design WP6-0, section C; AD-357, AD-374, AD-378, AD-380).

**Decision.**
1. Scan roots. The dual-run request carries `roots` (protocol `archkeel-dual-run-4`). The model binds them to the reply: each root must be the scope label that the collector wrote (`root/**` or `root`), one for each root, in order, without `*` (`Settings::bind_roots`). Other roots refuse the settings (exit 3). No roots name `Part::ScanRoots`. So a caller cannot widen a root by word.
2. Receipts (`model/src/receipts.rs`). `Scope::scan` gives a `ScanProof` only with bound roots and a profile whose files the core maps (`Layout::ProjectFiles`, from `archkeel-facts`; else `Part::ScanLayout`). The cycle receipts are `rules.py:516` and `:597` with `_cycle_scan_coverage`; the receipt of `complete_requires` is `scope_receipts_complete` with `_inside_rule_scope_is_complete`. A selector rule in the contract names `Part::ReceiptSources`. A receipt that fails is a fact (`Cause::Receipt`).
3. `no_component_cycles` (`eval/src/cycles.rs`): the component cycles of `Model::component_cycles` (the explicit stack of `condensation.rs`) and the module cycles of S3, with the rows of `rules.py:516` and `:597`. A dynamic import reaches a module rule always and a component rule from an owned module.
4. The drop rule with its cycle part (`model/src/pair_gaps.rs`, `check/pair_gaps.py`): a gap that can close a module or a component cycle is kept. A gap that it drops holds no rule; the run names it (`Part::AllowedPairGap`).
5. Pair-gap scope. A kept gap is no longer a fact of the whole state. Each rule kind states what it reads (`Reads`), and `Scope::gaps` gives the branded `GapScope` only when no kept gap can change that reading. `Scope::complete` needs it. A gap with an end that is not a module of the reply holds every rule. Else:

| Kind | Reads | A kept gap `a -> b` holds the rule when |
|---|---|---|
| `root_layout`, `layer_order`, `symbol_placement`, `allowed_dependency` | no edge | never |
| `complete_assignment` | the module set | never (an edge adds no module) |
| `external_dependency_scope`, `complete_external_scope` | direct external imports | `b` has an external import |
| `forbidden_dependency` | source side to target side | `a` matches the source side or has no one owner, and `b` the target side or has no one owner |
| `sibling_isolation` | edges at a member | `a` or `b` lies in a member |
| every other kind | every edge | always |

   Proof per kind: an internal edge adds no module, no file, no symbol and no contract value, so the first two rows read nothing that it changes. An external rule reads the direct imports of each source module; a method call of `a` into `b` adds no import of `a`, but `b` can re-export an external package, and the reply does not mark an external `pub use`, so any external import of `b` holds the rule. A forbidden edge needs both ends on their sides; an end without one owner can lie on either side. A peer edge needs an end in a member. A kind without this proof reads every edge.
6. The run stays UNKNOWN while any kept gap exists, and names the gaps. Each other cause (cfg gates, `include!`, unread files, limits, a tree) keeps its effect on every rule. An UNKNOWN text names at most 5 gaps and their number (`Held`).
7. The frame lists each PASS of a run with kept gaps in `beyond`. The harness shows it as `core decides, Python does not` only over a Python UNKNOWN of the same kind, and checks that the scope names the gaps.

**Reason.** 81 `complete_requires` rules and every cycle rule were named gaps without the roots. A kept gap made every rule UNKNOWN; most of those rules read no edge.

**Core decides, Python does not (point 5).** This is the one allowed direction change: Python gives UNKNOWN, the core PASS. 22 rules in 17 cases of the corpus (17 `complete_assignment`, 1 each of `root_layout`, `external_dependency_scope`, `complete_external_scope`, `forbidden_dependency`, `sibling_isolation`); listed in `docs/known-limits.md`.

**Differences that stay named.** The AD-374 recursion difference: Python stops with `maximum recursion depth exceeded` on a cycle or a chain of about 1 000 modules; the core walks with an explicit stack and decides the cycle rule (a 100 000-node cycle test). This is a decision where Python gives UNKNOWN, also named here.

**Rejected.** Roots as the word of the caller: a root `.` holds each file. An if-list of kinds in the core: the reading is a property of the proof. NEVER for the external kinds without the re-export condition: the reply cannot show a re-export. A gap dropped by the drop rule as a fact: it can only hide an edge that the contract allows.

**Limit.** Parity holds only for replies that the store accepts (TypeScript, Rust). Rules of a tree stay named gaps (AD-379).

**Corpus (645 cases, the ten decided kinds).** Both agree: `no_component_cycles` 151 PASS, 26 FAIL, 86 UNKNOWN; `complete_requires` 73, 38, 34 (0 PASS before). Core decides where Python differs: 0. Run status PASS or FAIL where Python differs: 0.

**Tests.** `native/model/src/roots_tests.rs`, `pair_gaps_tests.rs`, `settings_tests.rs`, `component_cycles_tests.rs`; `native/eval/src/gap_scope_tests.rs`, `scope_tests.rs`; the attempts 21 to 25 of `native/model-barrier`; `tests/test_native_core.py` (`BEYOND_CASES`); the 10 cases `s7/*`.
