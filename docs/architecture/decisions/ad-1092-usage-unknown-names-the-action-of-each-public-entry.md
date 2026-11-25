# AD-1092 `interface.usage_unknown` names the action of each public entry

**Status.** Accepted. Part of #1963 and #1919. It amends [AD-514](ad-514-the-core-proves-a-use-of-a-public-entry-from-imports-and-names-the-rest.md) (the lifecycle checks).

**Reason.** One text covered two cases: no import reaches the module of the entry, and an import of the module exists but proves no use of the entry. The first one asks for a delete. The second one asks for a read of the import. On EE 1,599 entries had the same text and no summary.

**Decision.**
1. `hygiene_interface` splits each `interface.usage_unknown` finding. An import (or a hop of a route) that targets the module of the entry gives `import_seen`. No such import gives `no_import_found`. The claim of each case has its own text.
2. A gap row of the frame gets the optional field `action`. Only a hygiene row of this kind writes it. Python reads it as the closed `GapAction` vocabulary and refuses another word.
3. The text of `validate` lists the exact count of each action under the kind, before the first rows.
4. The kind, the subject, the stable key and the verdict do not change. A baseline keeps matching.

**Rejected.**
- Two new gap kinds. Each baseline entry of the old kind would turn into a new gap, and the gates of EE and CE read the kind.
- Parsing the claim in the shell. The shell must not infer a word from text.

**Limit.** The text has no rollup by contract file and component.

**Tests.** `tests/test_cli_typescript_lifecycle.py::test_usage_unknown_names_the_action_of_each_entry`.
