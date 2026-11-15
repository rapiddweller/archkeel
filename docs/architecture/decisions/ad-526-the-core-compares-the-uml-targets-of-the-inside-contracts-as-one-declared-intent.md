# AD-526 The core compares the UML targets of the inside contracts as one declared intent

**Status.** Proposed. Part of #880. It extends AD-494 and AD-512 and replaces point 5 of AD-494.

**What 4.0.1 does** (`ir/target_graph.py` `declared_tree_graph`, `check/uml.py` `_target_records`):
the target of the tree is the entities, relationships and scopes of the root and of each mount in
one list. A mount id has the scope of its parent already. `compare_graphs` judges that one target
against the facts of the whole run; no mount clips it. Two planned entities of one qualified name
and language are refused (`duplicate planned entity`, exit 2).

**Decision.**
1. `archkeel_contract::merge_targets` joins the targets in order. It names no language.
2. `UmlTarget::Compare` carries `UmlDeclared`: the target of the root and of each mount that has
   one, with the place of the mount in the walk. `archkeel_model::compare_uml_tree` compares the
   joined target with the model of the root through `compare` (AD-494, AD-512). The comparison is
   the one of 4.0.1, so a missing import or an unlisted element is FAIL where 4.0.1 gives FAIL.
3. Two stops, before any comparison, with the cause named (`UmlGap::Nested`):
   - two contracts define the same element (qualified name and language, not a bare endpoint):
     4.0.1 refuses this tree, the core gives UNKNOWN;
   - a mount defines a module that the reply has and the source domain of that mount does not
     select (`Model::selects` of the mount model). 4.0.1 passes it; the core does not, because the
     inside scope of that target is not the scope of the mount.
4. PASS needs each assessment PASS and the scope proof of the whole run (`Scope::uml_complete`,
   the dropped pair gaps of AD-494 point 8). A gap inside or outside a mount keeps the row UNKNOWN:
   the core does not clip a gap to a mount, so no gap is shown not to change the row.
5. A mount in another language than the reply gives UNKNOWN (`module entity without one module`).
6. `UmlGap::Mounted` is removed.

**Where the core differs from 4.0.1.** Stricter only: the module outside the mount, the duplicate
entity and every gap give UNKNOWN where 4.0.1 gives PASS, a refusal or no row. The core gives no
PASS where 4.0.1 gives FAIL or no row.

**What the demos draw.** Every nested and every root target of H-uml-dart, I-flutter-shop,
J-compass, K-python-realworld and L-nest-realworld draws symbol elements (class, method,
attribute, function, enum, calls, realizes, inherits). Dart and Python have no symbol facts, so
those elements stay UNKNOWN by name. No fixture row moves to PASS; the cause of the row changes
from "an inside contract has its own UML target" to the assessments that no fact decides.

| run | row before | row after (cause) | 4.0.1 |
|---|---|---|---|
| H-uml-dart | UNKNOWN (own target) | UNKNOWN (89 assessments: no Dart symbol facts) | PASS |
| I-flutter-shop | UNKNOWN (own target) | UNKNOWN (289: no Dart symbol facts) | PASS |
| J-compass | UNKNOWN (own target) | UNKNOWN (421: no Dart symbol facts) | refused |
| K-python-realworld | UNKNOWN (own target) | UNKNOWN (307: no Python symbol facts) | PASS |
| L-nest-realworld | UNKNOWN (own target) | UNKNOWN (46: symbol inventory, closed scope) | refused |

**Plants** (`tests/uml_nested_plants.py`, 16 TypeScript trees; the 4.0.1 row was measured on the
same tree with `/private/tmp/oracle-401`, REFUSED means no row and exit 2):

| plant | 4.0.1 | core |
|---|---|---|
| nested-equal; nested-and-root-equal; inside-element-in-root-only; two-mount-levels | PASS | PASS |
| one-module-missing; mount-in-another-language; symbol-element; inside-target-without-element; same-element-in-two-forms | UNKNOWN | UNKNOWN |
| one-import-missing; one-import-missing-with-root-target; one-import-extra | FAIL | FAIL |
| module-outside-mount | PASS | UNKNOWN (outside the mount) |
| gap-inside-mount; gap-outside-mount | refused (parse_error) | UNKNOWN (scope not complete) |
| same-element-equal-twice | refused (duplicate planned entity) | UNKNOWN (both draw it) |
| mounted-contract-missing | refused | no row, the tree is unsupported |

**Mutations**, each run against the plants (the test that fails is the proof):

| mutation | failing tests |
|---|---|
| no duplicate stop | same-element-in-two-forms, same-element-equal-twice (row and cause) |
| no outside stop | module-outside-mount (row and cause) |
| the join ignores the mounts | one-import-missing-with-root-target |
| mount index shifted by one | module-outside-mount (row and cause) |
| root part dropped | both same-element plants (row and cause) |

**Finding to test.** The mount compare: `nested-equal` and the FAIL plants. The stops:
`test_an_unknown_nested_row_names_its_cause`. No PASS beyond 4.0.1:
`test_no_nested_plant_gives_a_pass_where_release_4_0_1_does_not`. The part order and the join:
`a_uml_target_in_an_inside_contract_is_compared_with_the_target_of_the_root` in
`contract_tests.rs`. The fixtures: `test_cli_fixture_matrix.py` (no pin moves).

**Rejected.** A per-mount clip of the facts: 4.0.1 has none, and a gap outside a mount cannot be
shown not to change an import of the target. A new rule kind: the row stays the one UML row of the
tree.

**Limits.** No Dart or Python symbol is compared. A module of a mount that the reply does not have
is UNKNOWN as before, not "outside".
