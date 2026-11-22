# AD-1043 A contract declares a trojan horse site by its name

**Status.** Accepted (owner decisions of 2026-11-22). Part of #1963. It amends [AD-664](ad-664-a-contract-can-declare-the-reach-of-a-door-site.md) and [AD-1042](ad-1042-a-trojan-horse-reach-names-its-reason-and-narrow-forms-are-proposed.md). Form (b) of AD-1042 replaces the proposed form words.

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice. The schema keys keep their old spelling in this change (`trojan_horse_reach`, `DoorForm`).

**Decision.**
1. Facts: `DoorSite` has `name` (the text that the gap prints), `exposed_to` (see 4) and an optional `form`. The Python collector states a site for each `dynamic_import`, `import_system_change` and `reexport_ambiguity` gap. Facts 11 is not in a release, so the fields are added in place (as `line_only` was). A stored file without them reads with the defaults.
2. Contract 3.20.0: a `trojan_horse_reach` record names its site by `trojan_horse` (a form) or by `name`, not both. `count` (one or more) is the number of sites with that key; the declaration applies to all of them or to none. The reader, the digest and the premise are the same as for forms. A moved site gives `trojan_horse_reach.unmatched`, a twin gives `ambiguous`; both stop the run as before. `rationale` stays required.
3. The premise is one text: the code that the site reaches imports only below `loads`, changes only below `changes`, and replaces no `sys.modules` entry, hook or builtin.
4. A declaration on an import statement applies only when no other module can reach the bound name. The model refuses it (`trojan_horse_reach.invalid`, the gap stays) when a module imports the name, star-imports the module, or uses an attribute or a text of that name while it imports the module or a package above it. The collector writes this list in `exposed_to`. A CPython plant shows the hole of AD-664: `import m; m.pickle.loads(blob)` in another module imported `app.lib` behind a declared `import pickle`.
5. Report: a rule that fails only through a declared `loads` edge reads "FAIL from a declared reach" (frame key `fail_from_declared_reach`, with the declaration ids, and the text). A PASS that rests on declarations reads "PASS assuming N declared reaches" with the list (id, site, reason).

**Limits.** The check of point 4 is by name; a name built at run time is the premise of the run (AD-770). The first version refuses a declaration when any other module reaches the name, instead of proving that each use is declared. `loads` is an upper bound, so a registry that declares its real loads can FAIL its own rule; the text names the declaration.

**Tests.** `tests/test_cli_python_door_name.py` (a name, a moved site, a twin and `count`, the `m.pickle.loads` plant with Python 3.12, FAIL from a declared reach), `contract/src/trojan_horse_reach_tests.rs`.

**Measured** (datamimic-ee `560d5c7ef`, a copy without `.git`, this build, no stand-in patch; 86 declarations by name, one source change: `authoring_service.py` reads `from importlib.metadata import version`).
- Baseline 223 UNKNOWN, 256 PASS. With `loads: []` for all: 24 UNKNOWN, 455 PASS, 0 FAIL, 199 rules read "PASS assuming 86 declared reaches".
- With the true loads of the registries: 24 UNKNOWN, 451 PASS, 4 FAIL (`DOMAINS-ACYCLIC`, `DOMAINS-REQUIRES`, `RUNTIME-TASKS-COMPLETE-REQUIRES`, `RUNTIME-TASKS-NO-COMPONENT-CYCLES`). Each reads "FAIL from a declared reach" with its declarations.
- The 24 UNKNOWN: 22 `interface_boundary`, 1 `forbidden_construct` pair, 1 UML target.
- Without the source change, one declaration is refused (`from importlib import metadata` in one module and an attribute `.metadata` in a module that imports it) and the 223 stay. datamimic-ce: one declaration is refused in the same way (`from importlib.resources import files` and an attribute `.files`), so its 99 UNKNOWN stay. The check by name is strict: it can refuse a safe declaration; it never applies an unsafe one.
- A cycle names components, so for a cycle every declaration that has a `loads` is listed as a cause.
