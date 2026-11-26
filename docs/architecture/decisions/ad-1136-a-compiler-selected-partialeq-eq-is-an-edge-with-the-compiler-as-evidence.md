# AD-1136: A compiler-selected `PartialEq::eq` is an edge with the compiler as evidence

Status: accepted. Amends AD-806 and AD-1047. Step 2 of the trait-dispatch path (step 1 is AD-1116).
This change can turn UNKNOWN into FAIL. Owner decision 2026-11-26: a proven dependency that the contract
does not allow must FAIL.

## Why

AD-806: if module C selects an impl in module M, C depends on M, with no written name. The scan kept only a
pair gap `C -> M`. A contract that forbids `C -> M` stayed UNKNOWN, also when the compiler selected the impl.
`Filter::excluded` (AD-1047) proves absence only. Nothing proved a presence.

## Decision

1. **Driver.** One `sel` record for each MIR call of `PartialEq::eq` that `Instance::try_resolve` resolves to
   the `eq` of a workspace trait impl, with operand types that hold no type parameter. A generic body, a `dyn`
   call, `&A == &B` (the impl is in `core`), `ne`, a default body and a foreign impl give no record. The record
   holds the two modules, the compiler path of the `eq`, and the file, line and column of the call.
2. **Reader.** The worker reads `sel` of non-test units only. The facts merge drops the `sel` records of a test
   unit before it merges them into the library file. The pair counts when both ends are different scan modules.
3. **Configurations.** A site gives an edge only when every configuration of the matrix holds it. Two edges that
   a cycle rule combines must come from one configuration, and an edge does not say which. A call behind one
   feature stays a gap.
4. **Edge.** `ImportFact::SelectedImpl` (wire kind `selected_impl`) goes from the caller to the module of the
   impl. It names no symbol and no publication route. The evidence is the call site, and only when the call is in
   the file of the caller module (the store refuses other evidence), and only when the selected `eq` is in the file
   of the target scan module. A module that is loaded from a file outside the scan is no ancestor.
5. **Open sites.** The edge comes after the flow knows its import edges, and it is not added to them. The pair
   gap stays for each site that the compiler did not resolve. One site proves the dependency, so a rule that
   forbids `C -> M` fails. `Filter::excluded` stays the single negative decision.
6. **Model.** `Import::selected_impl()` marks the edge. A rule that counts source names (AD-924) and the
   interface rule skip it: execution is no name (`Import::written_name`). In `complete_requires` a failing
   crossing is Undecided, never FAIL, when a port of the source can publish the type: the source has an entry for
   the target component, or a symbol port at the module of the impl or above it. The compiler names the defining
   module, not the facade that re-exports the type, and the core does not prove the route yet (#2069). The rule
   is UNKNOWN. When no other hold exists, the cause is "a selected impl of a type published through a port: the publication route is not
   proven (#2069)". An impl in a component that no entry of the source names still FAILs.

## Effect on the self-check (base 3af4cc4c259a)

- Base: 89 rules PASS, 3 UNKNOWN, 12947 gap records. Before the facade rule, CI showed 1 FAIL and 7 violations
  over 4 pairs into `typescript_collector.site_types`. The ports of `ts-sites` name `sites`, and the derive of
  `PartialEq` for `SiteKind` runs in `site_types`: now UNKNOWN, no FAIL.
- A local run found 3900 sites in 9 configurations. 1327 are in every configuration: 379 pairs of rustc modules.
- `graph.drift`: the compiler proves three component edges that the drawn graph missed: `core-baseline ->
  report-payload`, `core-engine -> model-terms`, `eval-rules -> model-match`. `native.md` draws them now.

## Counter-examples that were tried

Each is in `tests/test_cli_native_rust_selected_eq_edge.py` with the real driver, unless noted.
- `==` with a counter (`cargo run` prints 1) and a derived impl: FAIL. A return edge `b -> a`: cycle FAIL.
- `{}`, a drop, a held value, `&a == &b`, a generic helper, `Box<dyn>`, a test module: never FAIL.
- A call behind one feature: UNKNOWN (unit test). An allowing contract and a module port: PASS.
- A symbol port at the impl module or its parent, or a port of the target component that misses the impl
  module (a facade): UNKNOWN with the named cause. No entry for the target component: FAIL.
- Mutation: an edge without the compiler fact fails six unit tests. Without `written_name` the name rule turns UNKNOWN.

## Not done yet

- Only `PartialEq::eq`. `Display`, `Debug`, `Drop`, operators, `Deref` and `dyn` calls stay gaps.
- No symbol identity, and no configuration-aware edge.
- A saved reply carries the edge but no type-reach fact (AD-1116).
- The publication route (#2069): a facade port with the impl in the defining module stays UNKNOWN until proven.

## Checks

`native/rust/src/selected_edges_tests.rs`, `native/collect/src/rustc_facts_merge_tests.rs`,
`tests/test_cli_native_rust_selected_eq_edge.py` (needs `rustc-dev`), `make rustc-facts-e2e`.
