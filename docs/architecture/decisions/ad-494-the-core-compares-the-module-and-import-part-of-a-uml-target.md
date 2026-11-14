# AD-494 The core compares the module and import part of a UML target

**Status.** Proposed. Part of #880. It extends AD-470.

**What 4.0.1 compares** (`check/uml_compare.py`, `ir/source_graph.py`): the entities,
relationships and scopes of `declarations.uml` against the source facts. An entity passes for one
fact of its qualified name and language; a relationship passes for the resolved edge and fails
when it is absent from a complete inventory; a closed scope fails for each unlisted definition or
resolved edge. No module inventory is complete, so an absent module is UNKNOWN. Any FAIL makes
the row FAIL, any other UNKNOWN makes it UNKNOWN, else it is PASS.

**Decision.**
1. `archkeel_model::compare_uml` compares a root target with the model of the root, in
   `native/model/src/uml.rs` and `uml_scope.rs`. It reads the typed target of `archkeel-contract`;
   there is no second parser. The model names no language: an entity matches a module only when
   its `language` equals `Profile::language` of the reply.
2. Decided from module and import facts, with the 4.0.1 status or a stricter one:
   - a defined module entity: PASS for one module of its name, else UNKNOWN;
   - an `imports` relationship between two module entities: PASS for the resolved local edge,
     FAIL when it is absent and the scope of the run is complete, else UNKNOWN;
   - an open scope: PASS when its entity names one module or package;
   - a closed scope over modules and imports: FAIL for each unlisted module or resolved local
     import edge in it, else UNKNOWN.
3. Each other kind is UNKNOWN by name (`UmlGap::Undecided`): symbol entities and relationships, a
   module parent that is not a component, module details. They need symbol facts.
4. PASS needs every assessment PASS and `Scope::uml_complete`: the scope of the whole run is
   complete. The report writes PASS only when `Decision::passes` binds the row id and the root
   model. The row stays out of `decisions`. FAIL rows carry each differing fact as a detail.
5. A target in an inside contract keeps the row UNKNOWN (`UmlGap::Mounted`); 4.0.1 can pass it.
   An empty target and a target without an assessment stay UNKNOWN.
6. An `imports` endpoint that is not a module entity is UNKNOWN by name, as in `_matches`: a
   class, function, interface or package of a module name needs symbol facts. A package scope
   reads only packages; only a component scope falls back to a module of its name (`_scope`).
7. The contract owner refuses a `component` entity in `declarations.uml` (`contract.invalid`,
   exit 2): "UML cannot redeclare an existing component owner", as `intent_graph` of 4.0.1.
8. A dropped pair gap that touches a module of the target holds the row for a PASS and for a
   missing-import FAIL (`Scope::uml_run`): the gap can be an import edge of the target.
9. A FAIL for an extra element of a closed scope is true whatever the coverage, so it stays in an
   incomplete run. A closed scope without an extra element is UNKNOWN: it needs a complete
   inventory, which the core does not prove.

**Where the core differs from 4.0.1, with the proof.**
- Python `importlib.import_module('app.b.t')` or `__import__('app.b.t')` is an import edge since
  AD-472: a declared edge gives PASS (4.0.1: FAIL), and the edge under a closed scope without a
  listed import gives FAIL (4.0.1: PASS). The core reads the true edge; 4.0.1 misses it.
- TypeScript `import t = require('../b/t')` and a Dart conditional import under a closed scope:
  4.0.1 cannot complete the scan (exit 2, `parse_error`; its row is FAIL for TypeScript and
  UNKNOWN for Dart). The core gives FAIL for the true unlisted edge.
- Rust has no 4.0.1 comparison of a UML target. A Rust row rests on the scope proof alone,
  including the dropped pair gaps of point 8.

**Reason.** The UML row was always UNKNOWN, so each run with a target ended with exit 2. The
module and import part is decidable today and gives a real FAIL or PASS.

**Rejected.** Comparing symbol entities from the import records: they are not symbol facts.
A PASS for a subset of the assessments: a row needs each assessment.

**Limits.** No fixture row moves: each fixture target except J-compass names symbol entities,
and J-compass has coverage gaps. H-uml and H-uml-dart pass in 4.0.1 with symbol facts; they stay
UNKNOWN until a collector gives those facts. External and built-in import targets are not
compared (UNKNOWN), and a package entity is UNKNOWN.

**Tests.** `tests/test_cli_core_uml_compare.py`: 13 TypeScript plants with the 4.0.1 row and a
missing provenance file. `tests/test_cli_core_uml_target.py`: the fixture and refusal cases.
`tests/test_cli_core_uml_review.py`: the review forms (points 6 to 9 and the differences above)
in TypeScript, Python, Dart and Rust plants, and the component refusal.
