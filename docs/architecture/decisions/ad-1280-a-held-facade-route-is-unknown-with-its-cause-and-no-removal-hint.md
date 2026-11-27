# AD-1280 A held facade route is UNKNOWN with its cause and no removal hint

**Status.** Accepted. Closes #2198 (P0, release blocker). Builds on [AD-1171](ad-1171-a-usage-hold-names-the-cause-of-each-import-and-a-uml-hold-the-absent-symbols.md) and AD-1210.

**Reason.** A `public` entry reached through a facade re-export got `interface.usage_unknown` with the action `no_import_found` ("delete the entry or name the importer") when the collector withheld the route through the facade (a script outside the scan roots, an escaped module). The entry was in use. A team that followed the advice would narrow its public API by mistake. The action `import_seen` ("read the import or delete the entry") gave the same hint to an import with a stated cause.

**Decision.**
1. **Held route.** An import that reaches the component, names the entry's symbol, and states a withheld-route cause (AD-1210) is a held route. The gap gets the action `route_held` and the text "A route from an import to this entry is held, not absent ... the core does not recommend removing it", with the cause and the place of the first import (AD-1171). For a `module` entry without a symbol, an import of that module with a stated cause counts.
2. **Absent route.** `no_import_found` stays for an entry that no import of its name reaches, and keeps its removal hint. `import_seen` stays for an import without a stated cause (`other_symbol`, `call_form`, `unbound_type`).
3. **Proven route.** Unchanged: the entry is used and has no gap.
4. **Shell.** `GapAction.ROUTE_HELD`; the text is "route held, not proven: read the cause; the entry may be in use".
5. **Verdict.** No verdict, rule status or gap count moves toward PASS. The gap stays UNKNOWN; only its action and text change.

**Measured** (copies of EE `560d5c7ef` and CE `23bd48d9`, hold actions of `interface.usage_unknown`):

| | before | after |
|---|---|---|
| EE `no_import_found` / `import_seen` / `route_held` | 471 / 1,128 / 0 | 456 / 172 / 971 |
| CE `no_import_found` / `import_seen` / `route_held` | 273 / 525 / 0 | 269 / 20 / 509 |

Removal hints that disappear: EE 971 (15 from `no_import_found`, 956 from `import_seen`), CE 513 (4 and 509). The other 269 CE entries are named by no import across a component boundary (a use inside the component, or inside a mount); the hint stays true for them.

**Limit.** A held import of a name counts for each entry of that name in the component, also for an unrelated module with the same name. This only removes advice.

**Tests.** `tests/test_cli_python_held_route.py` (held route with its own facade component and with the facade in the component, proven route, unused entry, held route to another name); `tests/test_cli_python_usage_unknown_cause.py`. Mutation: with the held branch off, three of the six tests fail.
