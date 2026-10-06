# AD-162 Physical intent does not invent UML

The standard graph retains module inventories and root layout permissions.
No inventory means undeclared. An empty inventory means explicitly empty.
A file path and responsibility do not define a module's classes, methods or calls.
An allowed package does not have to exist.

`ContractModuleTarget` and `RootLayoutRule` have one definition in `ir.architecture_graph`.
Their `ir.model` exports remain compatible. Contract and graph codecs share their
path and immediate-child validation. The repository-path check also has one definition
in `ir.architecture_graph` with its compatible `ir.model` export. Contract 2.1 encoding stays unchanged.

`ModuleInventory` retains its scope, exact files and declaration provenance.
The graph rejects unsafe paths, duplicate inventories, missing owners and source
graphs carrying declared physical intent. Layout rules remain rules, not graph edges.

Core authenticates the existing physical declarations against the declaration revision.
The UML record references their IDs; it copies no inventory or layout contents.
The graph derives intent from these records. Its independent contract producer agrees.
Changed references or declaration contents fail authentication. The adapter gains no graph
or policy code.

Target/Diff Details shows file intent and layout permissions without placeholder cards
or selectable invisible elements.
This covers root Contract 2.2 intent. Legacy Target, nested inventories and global
API migration remain open. Existing Core rules still own physical validation;
UML comparison does not add a second physical verdict.

Proof: `tests/test_target_graph.py`, `tests/test_uml_rendering.py` and generated-schema checks.
