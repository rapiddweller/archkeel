# AD-494 The core compares the module and import part of a UML target

**Status.** Proposed. Part of #880. It extends AD-470.

**What 4.0.1 compares** (`check/uml_compare.py` `compare_graphs`, `ir/source_graph.py`).
The entities, relationships and scopes of `declarations.uml` against an observed graph of the
source facts. An entity passes when one fact has its qualified name and language; a declared
relationship passes when the resolved edge exists, and fails when it is absent from a complete
inventory; a closed scope fails for each unlisted definition or resolved edge in it. A module
inventory is never proven complete, so an absent module is UNKNOWN. Any FAIL makes the row FAIL,
any other UNKNOWN makes it UNKNOWN, else it is PASS. A component entity has no assessment.

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
3. Each other kind is UNKNOWN by name (`UmlGap::Undecided`): class, interface, function,
   attribute, constant, binding, symbol, enum and type alias entities; calls, references,
   inherits, realizes, creates and instance_of relationships; a module parent that is not a
   component; module details; closed scopes of other kinds. They need symbol facts.
4. PASS needs every assessment PASS and `Scope::uml_complete`: the scope of the whole run is
   complete. The report writes PASS only when `Decision::passes` binds the row id and the root
   model. The row stays out of `decisions`. FAIL rows carry each differing fact as a detail.
5. A target in an inside contract keeps the row UNKNOWN (`UmlGap::Mounted`); 4.0.1 can pass it.
   An empty target and a target without an assessment stay UNKNOWN.

**Reason.** The UML row was always UNKNOWN, so each run with a target ended with exit 2. The
module and import part is decidable today and gives a real FAIL or PASS.

**Rejected.** Comparing symbol entities from the import records: they are not symbol facts.
A PASS for a subset of the assessments: a row needs each assessment.

**Limits.** No fixture row moves: each fixture target except J-compass names symbol entities,
and J-compass has coverage gaps. H-uml and H-uml-dart pass in 4.0.1 with symbol facts; they stay
UNKNOWN until a collector gives those facts. External and built-in import targets are not
compared (UNKNOWN), and a package entity is UNKNOWN.

**Tests.** `tests/test_cli_core_uml_compare.py`: 13 TypeScript plants, each with the 4.0.1 row
(pass, missing edge, extra edge, extra module, an incomplete run, a renamed module, another
language, a class entity, a component or missing scope, a mounted target) and a missing
provenance file. `tests/test_cli_core_uml_target.py` keeps the fixture and refusal cases.
