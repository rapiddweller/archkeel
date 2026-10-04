# AD-169 Legacy permission scenes retain graph identities

Fresh report scenes read component details and import permissions from Core's
authenticated `ArchitectureGraph`. Permission IDs, endpoint IDs, rationale,
`through`, provenance and approval survive projection. Repeated permissions to
the same component remain distinct. A dependency endpoint is its real component,
including peers outside the opened level; it is not a placeholder rule card.

Root and nested scenes reuse one edge projector. Canonical endpoints resolve by
ID. Older snapshots without a graph descriptor keep their compatibility path.
Component roles and published/planned API intent remain inspectable. Permissions
allow imports; they do not assert an import, call or UML conformance verdict.

The shared renderer still owns arrows, routes, focus and hit geometry. Core,
analyzer policy and PR #277's process boundary are unchanged. Physical navigation,
legacy Diff and the remaining legacy payload migration stay open.

Proof: `tests/test_legacy_graph_rendering.py`; `make report-browser`.
