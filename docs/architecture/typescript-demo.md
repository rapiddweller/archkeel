# TypeScript import-graph demo

`fixtures/H-typescript` is a seven-module shop. The app composes data and
presentation; both depend on domain. The two data adapters stay independent.

Build the pinned collector explicitly, then run:

```bash
make -C packages/typescript-adapter install build
make demo-typescript OUTPUT=test-artifacts/typescript-demo-results
```

Every case copies the committed fixture, applies one catalog overlay and calls
normal `validate` and `report`. Each output directory retains source, contract,
validation/report JSON and, when report generation succeeds, `architecture.json`.
The replay invokes the public CLI. Fixed synthetic Git dates keep its source
commit identities stable across repeated runs on the same checkout.
Analysis does not install packages or execute the shop. Fixed package metadata
and declarations in `resolver-inputs` are copied into each committed snapshot
for reproducible external-package resolution. Host packages are not used.

`fixtures/demo_catalog_typescript.py` lists every rule kind and measurement.
`tests/test_typescript_demo.py` checks that the lists cover the current public
vocabulary and that actual outcomes match the catalog. Clean and changed cases
prove supported import-graph rules. Unsupported rules and budgets are refused.

| Evidence | Cases |
|---|---|
| Ownership and layout | clean, unassigned |
| Dependency direction and permissions | forbidden-type-import, requires, allowed-pair |
| Import cycles | component-cycle, module-cycle |
| Independent peers | sibling |
| External packages | external-allowed, external-forbidden, undeclared-external |
| Whole-module public boundary | module-interface, private-module |
| Incomplete evidence | computed-import, indirect-require, syntax-error |
| Unsupported rules | forbidden_construct, symbol_placement, boundary_types; target_symbol, named public and requires-through selectors |
| Unsupported scalar budgets | private_crossings, typing_positions, calls_unresolved, untyped_private_accesses |
| Unsupported name budgets | facade_names, coupling_names |

Type-only imports count for dependency direction. These are import cycles;
they do not establish runtime execution cycles. Computed imports prevent a
complete absence proof. Symbol, call, typing and private-use semantics are
unmeasured: their unavailable values cannot satisfy a budget.

File identity includes the repository path and extension. For example,
`src/domain/order.ts` maps to `shop.src.domain.order_x2e_ts`. A directory's
`index.ts` remains its own module.

Measurements checked independently:

- Clean: 7 modules, 8 internal import edges; zero violations and cycle edges.
- Cyclic: named SCCs and positive cycle-edge counts. A cycle inside domain stays absent from the component graph.
- Structure: module counts, inner edges and fan-in/out for all four components.
- Coverage and UNKNOWN: malformed input prevents complete measurements; computed imports remain undecided.
- Unmeasured: private crossings, typing positions, unresolved calls and untyped private accesses remain null. Call resolution is n/a.

Additional acceptance covers import forms, path-identity collisions, production
exclusions, runtime/declaration separation and non-execution of project plugins
and scripts. These are source-analysis checks, not evidence of shop runtime behavior.

The additional committed revision case uses a clean catalog overlay with explicit
TypeScript and JavaScript runtime inputs. A JavaScript-only comment changes the
source digest while the graph stays unchanged. The accepted lock uses schema 2.0.0;
the check reads both committed snapshots despite a poisoned working tree and
repeats identically. Host ordering and approval are simulated fixture evidence.
