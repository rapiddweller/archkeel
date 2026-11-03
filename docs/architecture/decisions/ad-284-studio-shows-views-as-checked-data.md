# AD-284 Studio shows views as checked data

**Status.** Accepted. Issues #784 and #785, epic #783.

**Decision.** A view is data, not a picture. An author (a person or an agent) writes a view
spec. `archkeel view check` checks each reference in it against one saved `architecture.json`.
1. Layer 1 is proof: the observed graph and the contract, read without an LLM. Layer 2 is
   author text: title, notes, step notes and each reference with `"claim": true`.
2. Fields: `schema_version`, `title`, `snapshot`, `nodes`, `edges`, `steps`, `notes`. A node is a
   top-level component id or a module name. An edge has `source`, `target`, `kind`, `claim`,
   `note`. A step has `node`, `note`, and `kind` and `claim` for the pair with the step before.
3. The check gives each node, edge and step one status:

   | Status | Meaning |
   |---|---|
   | `proven` | Observed relationships of the kind and direction, with record ids, evidence ids and lines. |
   | `declared` | Contract: a component, or a `requires` entry between two components. |
   | `claim` | Author text. The check does not look for it, also when the graph has the edge. |
   | `unknown` | The snapshot cannot decide: a coverage gap, a dynamic dependency, an unsupported node or kind. |
   | `missing` | Not in the snapshot, and the coverage of that kind is complete. |
4. Only a resolved relationship to a defined entity proves an edge. A step pair is proven by
   the shortest directed path of one kind. This is static structure, not runtime order: an
   import is not a call, and a path is not an execution trace. The Explorer must show that
   sentence with each proven step. No `kind` tries `imports`, then `calls`, never a mix.
5. `snapshot` names the `source_digest` and `contract_digest` the view describes. When they
   differ from the snapshot, the check does not run: each reference is `unknown`, exit 2.
6. The spec cannot state proof: an unknown field, for example `status` or `evidence`, makes it
   invalid in every mode. `--strict` also rejects each `unknown` reference.
7. Exit codes: 0 when no reference is `missing` (with `--strict`: and none is `unknown`);
   1 when one is; 2 when the check did not run: invalid input, or another snapshot.
8. `archkeel.ir.view_spec` is the one source; `make architecture-graph-schema` writes the schema.

**Rejected.** A server or a second renderer: the Explorer stays the only renderer (#786). Free
drawing and file descriptions: a second source of truth that ages. Proof by name prefix or by
reachability: a re-export or a dynamic call gives a wrong proof. A stale view checked against
other code: its notes describe the old code. A binding to the analyzer digest: each Archkeel
change makes each saved view stale, and the check proves each reference again anyway.

**Limits.** Each Python snapshot has a `dynamic_call_limit`, so a call edge is `unknown`, never
`missing`. A call through a re-export, for example `shop.store.OrderRepository`, proves no call
edge. Symbols and inside components are not nodes; an inside component id is `unknown`. A saved
flow in the contract that CI checks (#784, item 4) needs its own decision. Demo: planned.

**Checks.** `tests/test_cli_view.py`; `test_view_spec_schema_matches_its_dataclasses` in
`tests/test_schema_drift.py`. Example spec: `fixtures/F-architecture-view/place-order.json`.
