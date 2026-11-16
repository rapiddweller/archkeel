# AD-564 A gap states its effect and holds only the rules that read it

**Status.** Proposed. Part of #880. It extends AD-384 (pair gaps) and AD-500 (profile limits) to each coverage gap.

**Reason.** A coverage gap that is no pair gap makes the scope of the run incomplete (`coverage::incomplete`), so each rule of the run is UNKNOWN. One `exec` in one module holds a `root_layout` rule that reads no code. The release 4.0.1 ignores such a gap, which is a false PASS when the form is a real door.
**The facts of a module.** A collector writes three sorts of facts for a module `m`. `L(m)` is its file, name, package and blank flag. `E(m)` is the set of import edges that the code of `m` writes. `C(m)` is its code: members, positions, constructs and type shapes.

**Decision.**
1. `GapData.effect` (`GapEffect`) names the facts that can differ from the truth because of the gap.
   `edges {sources}`: `E(m)` of each source. `modules {modules}`: `E(m)` and `C(m)` of each module.
   `every_module`: `E` and `C` of every module. No variant contains `L`.
2. A gap without `effect` leaves the whole scope unknown, also `L`. So a collector that states no effect makes no verdict weaker. The pair form of AD-357 stays the only statement of one pair.
3. The model fails closed (`gap_class.rs`). An empty list, an effect on a pair-form gap, and a module that is not in the reply are the whole scope. A variant that the core does not know does not parse.
4. The duty of a collector: an effect names every module whose `E` or `C` the gap can change.
5. Each rule kind states the facts that it reads, in one `match` without a catch-all arm (`gap_effects::reads`). `Scope::complete` holds a rule when the effect of a gap meets its read set: the cause is `Cause::ScopedGaps`. A FAIL is decided before the scope, so a gap does not hide a violation that the scan sees. `Scope::run` fails with any such gap, so the run status and `uml_target` never pass with a gap.
6. The report names for each held rule the gaps that hold it (`scoped_gaps`), and for each PASS beside such gaps that no one of them can change the rule (`beyond`). The stable key of the cause names what is unknown (`edges: m`, `modules: m`, `every_module`) and no gap id, so a baseline entry stays valid when a gap moves to another line.
7. In a tree of mounts each model scopes these gaps for its own rules. A pair gap holds each rule of the tree (AD-385), because the reference engine does so. A gap with an effect has no such reference: `reads` tests each module against the modules that the model selects or that its components claim.

**Read sets.** A gap with a stated effect on module `X` holds a rule in these cases only. `every_module` holds each rule that is not in the first row.

| Rule kind | Reads | Held when |
|---|---|---|
| `root_layout`, `complete_assignment`, `layer_order`, `allowed_dependency` | `L` and the contract (`layout::check`, `assignment::check`, `direction::layers`; a permission has no verdict) | only a `layout` effect (AD-634) on a module below the root or the source; never for `layer_order` and `allowed_dependency` |
| `external_dependency_scope`, `complete_external_scope` | `E(m)` of each selected `m` in the source scope that the rule does not exempt | `X` is such an `m` |
| `forbidden_dependency` | `E(m)` of each selected `m` on the source side or without one owner, but not an allowed source; a `target_symbol` rule reads `C` of each module on the way to the symbol | `X` is such an `m`; for a symbol rule and `modules`: each `X` |
| `sibling_isolation` | `E(m)` of each selected `m` in a member scope | `X` is such an `m` |
| `complete_requires` | `E(m)` and `C(m)` (the `through` ports) of each `m` that a component claims | `X` is such an `m` |
| `interface_boundary` | `E(m)` of each claimed `m`; `C` of every module (a publication route) | `edges`: `X` is such an `m`; `modules`: each `X` |
| `no_component_cycles` | components: `E(m)` of each claimed `m`. Modules: `E` of every module | components: `X` is such an `m`; modules: each `X` |
| `forbidden_construct` | `E(m)` and `C(m)` of each selected `m` in the source scope; with a selector, of every module | `X` is such an `m`; with a selector each `X` |
| `boundary_types`, each kind that the core does not decide | no proof of a narrower reading | each `X` |
| `uml_target` | the run | each gap |

**Why it is sound.** Let `W` be the written facts and `T` the true facts. By item 4, `W` and `T` agree on each fact outside the effects of the gaps.
The evaluator and the receipt of a rule are functions of its read set. When no effect meets the read set, they read the same facts in `W` and in `T`, so a PASS on `W` is a PASS on `T`. A row of the table is thus sound when its read set contains every fact that the code of that kind reads. Each row names the function that reads. Where the code reads less than the row (a module that two components claim has no owner), the row keeps the wider set.

**Definitions.** These two sentences define the terms of the table. They are not premises that a project can fail.
- D1. `root_layout` and `complete_assignment` are rules on the files of the scan. No code adds a file to the scan, so only the `layout` effect of AD-634 contains `L`.
- D2. An edge is an import that the code of the source module writes (AD-500). A name that `m` gets through an attribute of another module is no edge of `m`.

**Owner decision: strict.** Text that the scan cannot see can replace a module in `sys.modules`, and then an import of any module gives another module than the one that it names. So each site that can run such text states `every_module`. No premise limits what the text does, and no option makes the effect narrower. `UNSEEN_CODE` in `survey/effects.rs` is the one switch.

**Effects of the Python collector** (`survey/effects.rs`, applied in `targets::site_gap`).
- `dynamic_import` (`exec`, `eval`, `compile`, a loader call with an unknown name) and `import_system_change`: `every_module`.
- `star_import` and `reexport_ambiguity`: `modules` of the source module. A star import binds names that the scan does not know and imports each submodule that `__all__` names.
- AD-634 adds the effects of the unresolved imports and of `module_outside_layout`, and of the TypeScript and Dart gaps.

**A loader call is not `edges` of its source module.** `importlib.import_module(name)` with an unknown name can return `sys`. The write `found.modules[__name__] = other` then gets no gap of its own, and each import of the module gives `other`. The plant `loader` proves it: with the mapping `edges {source}`, `CLIENT-NO-SECRET` is PASS while Python binds the secret module. A later change can state `edges` for a sound part: a call whose result the code does not use, or a name with a literal prefix below the project namespace.

**Rust.** The pair gaps of the Rust collector are scoped by AD-384 to one pair. Its module gaps state no effect yet (AD-634).

**Measured** on `efa899834`: before is this change with a mapping that states no effect, after is this change.

| Project | Rules | Decided before | Decided after | What holds the other rules |
|---|---|---|---|---|
| DATAMIMIC CE | 276 | 0 | 0 | 7 `module_outside_layout` gaps without effect; behind them the AD-500 limits of 6 `forbidden_construct` rules and 5 `measurement_budgets`. A work copy without these three: 176 of 270 (`root_layout` 151, `complete_assignment` 25); 35 `every_module` gaps hold 57 rules and 39 gaps hold 28 |
| pydantic | 5 | 0 | 1 | 49 `every_module` gaps and 108 `modules` gaps hold 3 `forbidden_dependency` and `complete_requires` |
| FastAPI | 3 | 0 | 2 | 2 `reexport_ambiguity` gaps hold `complete_requires` |
| graphql (TypeScript) | 8 | 0 | 0 | 2 script-global gaps without effect |
| `native/` (self) | 84 | 63 | 63 | 13 pair gaps (AD-384) |

**Rejected.**
- Rule ids or rule kinds in the gap. A collector does not know the contract.
- A table of reason texts in the model. It puts language knowledge into the model, and a renamed reason changes a scope silently.
- A narrow default for a gap without effect. An omission would make a verdict stronger.
- A `pair` variant. It is a second statement of the AD-357 pair, and two statements can differ.
- An undecided position for each import. A rule without a matching import would pass (AD-500).
- A premise that unseen text writes only to its own module. The plants `exec` and `loader` show a false PASS.

**Tests.** `gap_tests.rs`: the wire shape of each variant. `gap_class_tests.rs`: each doubt goes to the wider class; the key of the cause. `gap_effects_tests.rs`: the read set of each rule kind. `gap_effect_tests.rs` (eval): for each kind a gap in the read set keeps UNKNOWN, a gap outside lets the rule decide, and a violation behind a gap never passes. `effects_tests.rs`: the effect of each Python site kind. `test_cli_python_gap_effects.py`: seven plants through the release core; Python runs the hidden violation of three of them. 17 mutations of the read sets, the classes and the mapping: each one fails a test.
