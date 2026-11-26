# AD-1129: A compiler-selected `PartialEq::eq` is an edge with the compiler as evidence

Status: accepted. Amends AD-806 and AD-1047. Step 2 of the trait-dispatch path (step 1 is AD-1116).
This change can turn UNKNOWN into FAIL. Owner decision 2026-11-26: an honest, decided verdict. A proven
dependency that the contract does not allow must FAIL.

## Why

AD-806 says: if module C selects an impl in module M, C depends on M. C writes no name of M. Until now the
scan could only keep a pair gap `C -> M`. A contract that forbids `C -> M` stayed UNKNOWN, also when the compiler
selected the impl in C. `Filter::excluded` (AD-1047) proves absence only. Nothing proved a presence.

## Decision

1. **One kind of site.** The rustc driver writes a `sel` record for each MIR call of `PartialEq::eq` that the
   compiler resolves to the `eq` of a trait impl in the workspace. The driver resolves the call with
   `Instance::try_resolve` in the post-analysis environment. The operand types hold no type parameter.
   Other forms give no record: a generic body, a `dyn` call, `&A == &B` (the impl is in `core`), `ne`, a default
   method body and an impl of another crate. `PartialEq::eq` is the narrowest kind that a derive and a written
   impl share.
2. **The record.** `sel` holds the module of the call, the module of the impl, the compiler path of the selected
   `eq`, and the file, line and column of the call (`source_callsite`). A derived impl counts like a written one.
3. **The reader.** The Rust worker reads `sel` of non-test units only: a scan that leaves tests out must not charge
   test code to a module. It maps both modules to scan modules with the rule of the impls (`Reach::new`).
   The pair counts when both ends are different scan modules.
4. **The configurations.** A site gives an edge only when each configuration of the matrix holds it. Two edges
   that a rule combines (a cycle) must come from one configuration, and an edge does not say which. A call
   behind one feature stays a gap (UNKNOWN). A later change can carry the configuration.
5. **The edge.** `ImportFact::SelectedImpl` (wire kind `selected_impl`) is a typed kind of the `imports`
   section. The record goes from the caller to the module of the impl. It names no symbol and no publication
   route (`symbols_known` false). The evidence is the call site. The worker writes it only when the call is in the
   file of the caller module: the store refuses other evidence. An `include!` or a `#[path]` module stays a gap.
6. **Other sites stay open.** The worker writes the edge after the flow knows its import edges, and it never adds
   the edge to them. The pair gap `C -> M` stays for each site that the compiler did not resolve (a drop, a format,
   a `dyn` call). One site proves the dependency, so a rule that forbids `C -> M` fails. A rule that needs the
   whole pair, and a contract that allows the pair, see the open gap as before. `Filter::excluded` stays the
   single negative decision.
7. **The model.** `Import::selected_impl()` marks the edge. It is an import for `forbidden_dependency`,
   `complete_requires` and the cycle rules. Two rules read it differently:
   - A rule that counts source names (`source_symbol_only`, AD-924) skips it: execution is no name
     (`Import::written_name`). The interface rule skips it too.
   - `complete_requires`: when the crossing fails and the source has a symbol port at the module of the impl or
     above it, the judgement is Undecided. The compiler names the module of the impl, not the symbol that a port
     publishes. A symbol port in an unrelated module does not hide the violation.

## Effect on the self-check (`make self-check`, base 3af4cc4c259a)

- Base: 89 rules PASS, 3 UNKNOWN, 12947 gap records, no violation.
- This change: 89 PASS, 2 UNKNOWN, 1 FAIL, 12948 gap records, 1 violation.
- The driver wrote 3900 sites in 9 configurations. 1327 sites are in every configuration. They cover 379 pairs
  of rustc modules, 96 of them across crates. Most pairs are inside one component or allowed by a port.
- New FAIL: `NATIVE-REQUIRES-COMPLETE` (was UNKNOWN), one pair:
  `typescript_collector.site_records -> typescript_collector.site_types` (`site_records.rs:295`, `SiteKind::New`).
  The ports of `ts-sites` name `sites` and the other facade modules, and not `site_types`, where the derive of
  `PartialEq` for `SiteKind` runs. The contract is not changed here.
- New gap: one `graph.drift` hygiene gap. The drawn graph misses two proven component edges:
  `core-baseline -> report-payload` and `eval-rules -> model-match`.

## Counter-examples that were tried

Each is a test in `tests/test_rust_selected_eq_edge.py` that runs the real driver, unless noted.
- `==` on a factory result, impl in `b`: the counter of `cargo run` is 1, the contract FAILs. A derived impl FAILs too.
- `{}` on a factory result (`Display` in `d`): no site, the pair stays UNKNOWN.
- A drop with a `Drop` impl, a value that is only held, `&a == &b`, a generic helper, a `Box<dyn Trait>` call: no
  site, never FAIL.
- A call behind one feature: no edge, UNKNOWN. The Rust unit test checks the intersection.
- A return edge `b -> a` with the selected edge `a -> b`: the module cycle FAILs.
- A contract that allows the edge passes. A module port that covers the impl passes. A symbol port at the module
  of the impl or above it is UNKNOWN. A symbol port in an unrelated module FAILs.
- A rule that counts written names passes.
- Mutation: the edge without the compiler fact (a fabricated edge) fails six unit tests. Without `written_name`
  the name rule turns UNKNOWN and its test fails.

## Not done yet

- Only `PartialEq::eq`. `Display`, `Debug`, `Drop`, operators, `Deref` and `dyn` calls stay gaps.
- No symbol identity: a symbol port stays UNKNOWN. A later change can match the self type of the impl to the
  symbol of a port through its publication route.
- A configuration-aware edge. A site behind one feature gives no edge.
- A saved reply carries `selected_impl` records, but it carries no type-reach fact (AD-1116): the premise
  `rust_type_reach` is still named only for a live scan.
- The re-export case: a facade module in the ports and the impl in the defining module (`sites` and `site_types`)
  is a FAIL now. The owner decides between a port and a publication-route proof.

## Checks

`native/rust/src/selected_edges_tests.rs` (six cases of the reader and the edge), `tests/test_rust_selected_eq_edge.py`
(the fixture runs with `cargo run`; needs `rustc-dev`), `make rustc-facts-e2e` (the driver on all hole fixtures).
