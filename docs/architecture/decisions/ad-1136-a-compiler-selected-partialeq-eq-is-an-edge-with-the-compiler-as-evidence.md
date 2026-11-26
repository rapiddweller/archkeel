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
   the file of the caller module: the store refuses other evidence.
5. **Open sites.** The edge comes after the flow knows its import edges, and it is not added to them. The pair
   gap stays for each site that the compiler did not resolve. One site proves the dependency, so a rule that
   forbids `C -> M` fails. `Filter::excluded` stays the single negative decision.
6. **Model.** `Import::selected_impl()` marks the edge. A rule that counts source names (AD-924) and the
   interface rule skip it: execution is no name (`Import::written_name`). In `complete_requires` a failing
   crossing is Undecided when the source has a symbol port at the module of the impl or above it. The compiler
   names the module, not the symbol that a port publishes (follow-up: #2069).

## Effect on the self-check (`make self-check`, base 3af4cc4c259a)

- Base: 89 rules PASS, 3 UNKNOWN, 12947 gap records. This change: 89 PASS, 2 UNKNOWN, 1 FAIL, 12948 gap records.
- The driver wrote 3900 sites in 9 configurations. 1327 are in every configuration: 379 pairs of rustc modules,
  96 across crates. Most pairs are in one component or allowed by a port.
- New FAIL: `NATIVE-REQUIRES-COMPLETE` (was UNKNOWN), one pair:
  `typescript_collector.site_records -> typescript_collector.site_types` (`site_records.rs:295`). The ports of
  `ts-sites` name `sites` and not `site_types`, where the derive of `PartialEq` for `SiteKind` runs.
- New gap: one `graph.drift` gap. The drawn graph misses `core-baseline -> report-payload` and
  `eval-rules -> model-match`.

## Counter-examples that were tried

Each is in `tests/test_rust_selected_eq_edge.py` with the real driver, unless noted.
- `==` with a counter (`cargo run` prints 1) and a derived impl: FAIL. A return edge `b -> a`: cycle FAIL.
- `{}`, a drop, a held value, `&a == &b`, a generic helper, `Box<dyn>`, a test module: never FAIL.
- A call behind one feature: UNKNOWN (unit test). An allowing contract and a module port: PASS.
- A symbol port at the impl module or its parent: UNKNOWN. A symbol port elsewhere: FAIL.
- Mutation: an edge without the compiler fact fails six unit tests. Without `written_name` the name rule turns UNKNOWN.

## Not done yet

- Only `PartialEq::eq`. `Display`, `Debug`, `Drop`, operators, `Deref` and `dyn` calls stay gaps.
- No symbol identity, and no configuration-aware edge.
- A saved reply carries the edge but no type-reach fact (AD-1116).
- A facade port with the impl in the defining module (`sites`, `site_types`) is a FAIL now.

## Checks

`native/rust/src/selected_edges_tests.rs`, `native/collect/src/rustc_facts_merge_tests.rs`,
`tests/test_rust_selected_eq_edge.py` (needs `rustc-dev`), `make rustc-facts-e2e`.
