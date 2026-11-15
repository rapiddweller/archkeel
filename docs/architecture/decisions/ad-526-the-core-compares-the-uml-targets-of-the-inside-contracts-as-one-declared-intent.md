# AD-526 The core compares the UML targets of the inside contracts as one declared intent

**Status.** Proposed. Part of #880. It extends AD-494 and AD-512 and replaces point 5 of AD-494.

**What 4.0.1 does** (`ir/target_graph.py` `declared_tree_graph`): the target of the tree is the
entities, relationships and scopes of the root and of each mount in one list; a mount id has the
scope of its parent. `compare_graphs` judges it against the facts of the whole run, with no clip
to a mount. Two planned entities of one name and language are refused (`duplicate planned entity`).

**Decision.**
1. `merge_targets` (`native/contract`) joins the targets in order and names no language.
2. `UmlTarget::Compare` carries `UmlDeclared`: the target of the root and of each mount that has
   one, with the place of the mount in the walk. `compare_uml_tree` joins them and calls the
   `compare` of AD-494 and AD-512, so a missing import or unlisted element is FAIL as in 4.0.1.
3. Two stops with a named cause (`UmlGap::Nested`), before any comparison: two contracts define
   one element (4.0.1 refuses the tree); a mount defines a module that the reply has and the
   source domain of the mount does not select (`Model::selects`; 4.0.1 passes it).
4. PASS needs each assessment PASS and `Scope::uml_complete` for the whole run. A gap inside or
   outside a mount keeps the row UNKNOWN: no gap is shown not to change an import of the target.
5. A mount in another language than the reply is UNKNOWN. `UmlGap::Mounted` is removed.

**Differences from 4.0.1.** Stricter only: UNKNOWN where 4.0.1 passes (module outside the mount),
refuses (duplicate entity, a gap that stops its scan) or gives no row. No PASS where 4.0.1 gives
FAIL or no row.

**What the demos draw.** Each root and each nested target of H-uml-dart, I-flutter-shop,
J-compass, K-python-realworld and L-nest-realworld draws symbol elements. Dart and Python have no
symbol facts, so no fixture row moves to PASS; the cause changes from "an inside contract has its
own UML target" to the assessments that no fact decides (H-uml-dart 89, I-flutter-shop 289,
J-compass 421, K-python-realworld 307, L-nest-realworld 46). 4.0.1: PASS, PASS, refused, PASS,
refused.

**Plants** (`tests/uml_nested_plants.py`, 16 TypeScript trees; the 4.0.1 row is measured on the
same tree): PASS in both: nested equal, nested and root equal, inside element in the root only,
two mount levels. UNKNOWN in both: module missing, other language, symbol element, empty inside
target, one element in two forms. FAIL in both: import missing (also with a root target), import
extra. Module outside the mount: 4.0.1 PASS, core UNKNOWN. Gap inside or outside a mount, equal
element twice, mount file missing: 4.0.1 refuses, core UNKNOWN or no row.

**Mutations** (each fails the named plants): no duplicate stop (both same-element plants); no
outside stop (module outside the mount); the join ignores the mounts (import missing with a root
target); mount index shifted (module outside the mount); root part dropped (both same-element
plants).

**Tests.** `test_cli_core_uml_nested.py`, `test_cli_core_uml_target.py`, `contract_tests.rs`.

**Rejected.** A clip of the facts per mount: 4.0.1 has none. A new rule kind.

**Limits.** No Dart or Python symbol is compared. A module of a mount that the reply lacks is
UNKNOWN as before.
