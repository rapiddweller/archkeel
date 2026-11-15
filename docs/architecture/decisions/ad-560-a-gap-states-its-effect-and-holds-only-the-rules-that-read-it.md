# AD-560 A gap states its effect and holds only the rules that read it

**Status.** Proposed. Part of #880. It extends AD-384 (pair gaps) and AD-500 (profile limits) to each coverage gap.

**Reason.** A coverage gap that is no pair gap makes the scope of the run incomplete (`coverage::incomplete`), so each rule of the run is UNKNOWN. One `exec` in one module holds a `root_layout` rule that reads no code. The release 4.0.1 ignores such a gap, which is a false PASS when the form is a real door. Measured on `2b58c0a14`:

| Project | Rules | Decided | Gaps |
|---|---|---|---|
| DATAMIMIC CE | 276 | 0 | 59: `dynamic_import` 47 (in 11 modules), `module_outside_layout` 7, `reexport_ambiguity` 4, `import_system_change` 1 |
| pydantic | 5 | 0 | 321: `dynamic_import` 206, `reexport_ambiguity` 98, `star_import` 10, `import_system_change` 7 |
| FastAPI | 3 | 0 | 6: `dynamic_import` 4, `reexport_ambiguity` 2 |
| graphql (TypeScript) | 8 | 0 | 6 script-global gaps |
| `native/` (self) | 84 | 63 | 59 pair gaps, which AD-384 scopes already |

**The facts of a module.** A collector writes three sorts of facts for a module `m`. `L(m)` is its file, name, package and blank flag. `E(m)` is the set of import edges that the code of `m` writes. `C(m)` is its code: members, positions, constructs and type shapes.

**Decision.**
1. `GapData.effect` (`GapEffect`) names the facts that can differ from the truth because of the gap.
   `edges {sources}`: `E(m)` of each source. `modules {modules}`: `E(m)` and `C(m)` of each module.
   `every_module`: `E` and `C` of every module. No variant contains `L`.
2. A gap without `effect` leaves the whole scope unknown, also `L`. So a collector that states no effect makes no verdict weaker. The pair form of AD-357 stays the only statement of one pair.
3. The model fails closed. An empty list, an effect on a pair-form gap, and a module that is not in the reply are the whole scope. A variant that the core does not know does not parse.
4. The duty of a collector: an effect names every module whose `E` or `C` the gap can change.
5. Each rule kind states the facts that it reads, in one `match` without a catch-all arm, beside
   `pair_gaps::reads`. `Scope::complete` holds a rule when the effect of a gap meets its read set.
   The cause names the ids of these gaps. `Scope::run` fails with any gap, so the run status and
   `uml_target` never pass with a gap.
6. The report names for each rule the gaps that hold it. A baseline key names each gap id.
7. The first change adds only the field. The model does not read it, so each gap holds every rule. Each later change adds its measured row to this record.

**Read sets.** A gap with a stated effect on module `X` holds a rule in these cases only:

| Rule kind | Reads | Held when |
|---|---|---|
| `root_layout`, `complete_assignment` | `L` and the contract (`layout::check`, `assignment::check`) | never |
| `layer_order`, `allowed_dependency` | the contract only (`direction::layers`; a permission has no verdict) | never |
| `external_dependency_scope`, `complete_external_scope` | `E(m)` of each selected `m` in the source scope that is not an allowed source | `X` is such an `m` |
| `forbidden_dependency` | `E(m)` of each selected `m` on the source side or without one owner; a `target_symbol` rule reads `C` of the target too | `X` is such an `m`; for a symbol rule and `modules`: each `X` |
| `sibling_isolation` | `E(m)` of each selected `m` in a member scope | `X` is such an `m` |
| `complete_requires`, `interface_boundary`, `no_component_cycles` of components | `E(m)` of each `m` that the model selects or a component claims; `interface_boundary` reads `C` of the target | `X` is such an `m` |
| `no_component_cycles` of modules | `E` of every module of the reply | each `X` |
| `forbidden_construct` | `C(m)` of each selected `m` in the source scope; with a selector `C` of every module | `X` is such an `m`; with a selector each `X` |
| `boundary_types`, each kind that the core does not decide | no proof of a narrower reading | each `X` |
| `uml_target` | the run | each gap |

**Why it is sound.** Let `W` be the written facts and `T` the true facts. By item 4, `W` and `T` agree on each fact outside the effects of the gaps.
The evaluator and the receipt of a rule are functions of its read set. When no effect meets the read set, they read the same facts in `W` and in `T`, so a PASS on `W` is a PASS on `T`.
A row of the table is thus sound when its read set contains every fact that the code of that kind reads. Each row names the function that reads.

A plant for each kind checks its row: a gap in the read set keeps UNKNOWN, and a violation behind a gap never passes.
A mount reads only the modules that it selects or that its components claim, so a gap outside holds no rule of the mount.

**Premises. The owner can veto each one.**
- P1. Code that a door of `m` runs (`exec`, `eval`, a loader call) is code of `m`. It changes no import system and writes to no other module. Without P1, `dynamic_import` must be `every_module`.
- P2. `root_layout` and `complete_assignment` are rules on the files of the scan. An import-system change adds no file. Without P2, `import_system_change` must state no effect.
- P3. An edge is an import that the code of the source module writes (AD-500). A name that `m` gets through an attribute of another module is no edge of `m`.

**Effects of the Python collector (later change).** `dynamic_import` and `star_import`: `modules` of the source module. `reexport_ambiguity`: `edges` of the source module. `import_system_change`: `every_module`. A file gap (`module_outside_layout`, `duplicate_module`, `stub_or_compiled_module`, `unreadable_source`, `linked_source`) states no effect, because `L` is not known.

**Rejected.**
- Rule ids or rule kinds in the gap. A collector does not know the contract.
- A table of reason texts in the model. It puts language knowledge into the model, and a renamed reason changes a scope silently.
- A narrow default for a gap without effect. An omission would make a verdict stronger.
- A `pair` variant. It is a second statement of the AD-357 pair, and two statements can differ.
- An undecided position for each import. A rule without a matching import would pass (AD-500).
- A narrower read set for a type-only import. No project measured here needs it.

**Tests.** `gap_tests.rs`: the wire shape of each variant, a gap without effect keeps its bytes, an unknown variant is refused.
