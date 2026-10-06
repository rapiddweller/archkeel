# TypeScript import-graph demo

Replay the committed shop fixture with the collector that ships in the package:

```bash
make demo-typescript OUTPUT=test-artifacts/typescript-demo-results
```

Each case copies `fixtures/H-typescript`, applies a catalog overlay and invokes
the public CLI. Outputs retain source, policy, result JSON and, when generated,
`architecture.json`. Analysis uses committed resolver inputs, not host packages,
and does not execute the shop or its scripts.

The [catalog](../../fixtures/demo_catalog_typescript.py) covers ownership, layout,
dependency permissions, cycles, peers, externals and whole-module interfaces.
[Acceptance tests](../../tests/test_typescript_demo.py) check actual outcomes and
the supported vocabulary. Unsupported rules and budgets are refused; incomplete
import evidence remains UNKNOWN. Type-only imports count as dependencies, not
proof of runtime execution cycles.

A committed revision case also proves that JavaScript inputs affect the source
digest, snapshots survive a poisoned working tree and replay is deterministic.
Its host ordering and approval are simulated fixture evidence. See the
[adapter decision](typescript-foundation-proposal.md#evidence-and-limits) for limits.
