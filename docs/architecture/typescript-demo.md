# TypeScript demos

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

`make demo-uml OUTPUT=test-artifacts/uml` also generates native TypeScript UML reports.
The `uml-typescript-match`, `uml-typescript-mismatch` and `uml-typescript-partial` variants
exercise matching intent, a changed method signature and an unresolved constructor.
Their Target is declared independently in `fixtures/H-uml-typescript`; it is never copied
from observed facts. Reports use the shared As-Is, Target and Diff views.

Classifiers, members, signatures, visibility, static members and proven local relationships
carry source locations. Missing members require complete inventory for that owner and kind.
Computed or ambiguous bindings remain UNKNOWN; a complete import scan does not prove them.

The shop demo independently declares all seven modules down to UML: 17 entities and
14 relationships. Its ten undecided positions remain visible; declaring intent does not
turn incomplete observation into PASS.
