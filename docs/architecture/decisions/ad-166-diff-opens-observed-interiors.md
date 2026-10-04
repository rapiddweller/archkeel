# AD-166 Diff opens observed interiors

An observed class does not need a unique Target counterpart to expose its methods.
Diff opens recorded interiors through the same projection and UML renderer as As-Is.

Each navigation entry retains the graph origin and raw entity ID. Activation uses
the visible scene's entity and graph; it never decodes an ID prefix or matches names.
Breadcrumbs label observed entries. Back navigation restores the same source card.
The existing history restores scope, position, selection and keyboard focus, including
methods opened directly from Details. Each tab keeps its own scope and selection.

Children and outgoing relationships make an interior openable. This includes an
operation's call graph. Details reads the current scope when no card is selected.
Observed interiors show Core receipts by their observed IDs, not Target IDs.
No counterpart, assessment or verdict is invented. An unassessed observed scope
says so. Unresolved sites remain in Details without clickable endpoint cards.

No graph schema, adapter, observation format or Core policy changed.
Proof: `tests/test_uml_rendering.py`; `make report-browser`.
