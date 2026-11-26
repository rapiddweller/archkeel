# AD-1160: The facts of a bin target belong to its bin modules

Status: accepted. Amends AD-1047. Part of #2084; follow-up #2096.

## Why

The nine NATIVE-NO-MODULE-CYCLES candidates of the self-check (AD-1047, `designs/CYCLES-9.md`) each have a real
reverse source use and a possible trait-impl dispatch. The first measurement (11 pairs on 2026-11-26) found two causes.

1. Three pairs in `scip_evidence` had no compiler facts (`Cause::NoFacts`). The scan names the modules of
   the `main.rs` of a package `<namespace>.<package>.bin_<crate>.<module>` (`crates.rs`). The facts name them
   `<crate>::<module>`. The reader found no such scan module and cut the name back to the crate root, so the facts of
   a bin module were counted under the library root.
2. The other pairs are kept as `Reached`. The reach of a module of 28 to 50 own types grows to about 1200 types: the
   coercions to `dyn Fn` are recorded under the trait name only, so one `&dyn Fn(..)` in reach brings the captured
   types of every closure that a body coerces to any `dyn Fn`; the flow over calls outside the workspace (`via`)
   adds the rest. See #2096.

## Decision

1. `bin_module` in `native/rust/src/type_reach_fold.rs` maps a facts path to the module of the single scan target
   `bin_<crate>`. The facts carry no split by target: the unit of the library holds the modules of `main.rs` too
   (measured), so the scan decides, for a crate with a `bin` unit in the facts. A path keeps the library when a scan module of the library below the crate root
   owns it (also by an inline module), and when no scan module below `bin_<crate>` owns it. An inline module at the
   crate root of the library therefore stays with the crate root. Two targets with the same name give no mapping.
2. No rule, no gap text and no verdict logic changes. The reach of a module stays as it was.
3. The remaining pairs are not decided here. Each one stays UNKNOWN with the measured cause above. A
   contract unit option (#1013) or a weaker rule is not used.

## Measured (`ARCHKEEL_ALLOW_BUILD=1`, native/archkeel.toml, same revision, without and with the change)

| | without | with |
|---|---|---|
| NATIVE-NO-MODULE-CYCLES held pairs | 11 | 10 |
| NATIVE-REQUIRES-COMPLETE held pairs | 8043 | 8042 |
| NATIVE-INTERFACE-BOUNDARY held pairs | 1207 | 1207 |
| gaps | 13049 | 13037 |

Experiments on the model (unsound, a measurement and no proof): no `via` flow gives 4 pairs; no types for `dyn Fn`
gives 1 pair and 12072 gaps.

## The nine pairs, one by one

Child to parent (8): `pyast.node`, `pyast.children` to `pyast` (`Walk`, `Iterator`); `hazards.bind` to `hazards`
and to `hazards.comprehension` (`Walk`, `Visitor`; `Targets`, `Trojans`, `Assigns`, `Declared`);
`hazards.comprehension` to `hazards`; `impl_edges.orphans` to `impl_edges` (`Builder`);
`scan.receivers.params` to `scan.receivers` (`Frame`, `Selves`); `scip_evidence.syntax` to `scip_evidence`.
Sibling (1): `scip_evidence.syntax` to `scip_evidence.bindings`.

- Witness (a real child to parent dispatch, FAIL): none found. No child names, builds or receives a value of the parent
  type that the held impl belongs to (`CYCLES-9.md`).
- Complete exclusion (PASS): not proven. The reach model keeps each pair as `Reached` through the `dyn Fn` merge and the `via` flow.
- Missing proof: #2096. Moving the impl type does not help: the reach is global, so a new home of the impl gets the same
  potential edge from every module, and a home with no real edge back to the child does not exist for `Walk::next`.

## Not done yet

The reach of the held modules. A library inline module and a bin module with the same name below the same crate root cannot be told apart by the scan alone: the facts of that name go to the library module. A planted sibling cycle is still caught: the rule reads real edges, and the change adds none.
