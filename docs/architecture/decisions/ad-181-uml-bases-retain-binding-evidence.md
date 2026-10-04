# AD-181 UML bases retain binding evidence

The Python symbol collector records each explicit base expression with its source site,
relationship kind and resolution limits. A stable direct module binding can prove one
classifier. Repeated definitions remain candidates. Rebinding, replaceable classes, lexical
lookup, unknown external kinds and custom generic origins remain partial or unresolved.
Expressions are never executed.

A class explicitly implementing a known Protocol records `realizes`. A subprotocol records
`inherits`. This does not infer structural implementation from matching method signatures.
Legacy base-name arrays alone prove neither typed edges nor complete coverage.

`ir.source_graph` projects these facts into the shared relationship dataclass and retains
their class record IDs and source evidence. Each recorded classifier has its own base-list
coverage. Module coverage remains partial while conditional classifiers are not inventoried.
Core uses the nearest covering receipt and retains descendant limits. A complete local list
can prove a missing base; an unresolved base cannot. Child receipts alone cannot certify
an unmeasured parent inventory or prove a missing sibling.

Adapters collect syntax and binding evidence. IR normalizes facts. Core evaluates the
independent Target. Rendering owns no new inference or verdict.

Proof: `tests/test_uml_classifier_facts.py`, `tests/test_uml_comparison.py`,
`tests/test_source_graph.py`; `make self-validate` and `make self-observation`.
