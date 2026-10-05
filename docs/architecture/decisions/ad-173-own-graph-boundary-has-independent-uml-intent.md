# AD-173 Own graph boundary has independent UML intent

The IR contract declares the shared graph's classes, fields, validation methods,
producer/codec functions and typed imports/calls/references. These values are authored from
the approved model boundary, without loading source observations or copying a scan.

Classes remain immutable. Public validation checks IDs, references and value
invariants; private helpers own individual checks. Producers return the same graph
type. Core still owns authentication, comparison and architecture verdicts.

Planned fields need a classifier parent. Inheritance and realization reject known
non-classifier endpoints; unclassified external references remain valid.
Planned UML identity uses name, kind, language, lexical parent and signature. Another ID,
responsibility or provenance does not create distinct intent. Different overload signatures
and observed definition-site IDs remain valid. Component owners retain separate architectural
containment. Python signatures cannot repeat parameter names.

Twelve declared class dependencies connect the shared value types. A signature
uses parameters; an entity uses visibility and signatures; Target and graph
values use entities, relationships, coverage and scopes. Comparison uses
assessments and correspondences. These are UML dependencies, not assertions
about runtime ownership or lifetime.

This first inner Target covers the shared graph boundary. Other IR helpers and
components remain open work. No closed inventory or full-target claim is added.

Proof: `tests/test_own_uml_target.py` checks the intended boundary and changes an
observed method signature. The unchanged Target must report FAIL for that change.
Field and value-binding records describe separate roles of one assignment. Core
matches their kinds separately; repeated field definitions remain UNKNOWN, and a
binding without the declared field fails the kind check. Imports use module
endpoints; they do not claim a complete inventory of imported members.
Type-reference proof checks all twelve dependencies. Removing a reference leaves
UNKNOWN under partial coverage; a certified complete inventory must report FAIL.

Operation views retain caller and callee identities instead of folding methods
into their owning classes. All three views use the same scene projection.
Browser proof covers own private helper calls and calls to another class's method.
