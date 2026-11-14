# AD-504 The Python survey writes the publication route of each named import

**Status.** Proposed. Part of #880. It amends AD-450 (the survey states no interface) and AD-500
(which statements hold which rule). The hygiene checks `interface.*` follow in a second change.

**Reason.** `interface_boundary` on Python was UNKNOWN for each rule: the linked survey stated
`interface_boundary: Unsupported`. Release 4.0.1 decides it (M-review-workflow: 12 PASS). The core
already decides this rule for TypeScript, from one seam: the import records carry `symbol` and
`reexport_chain`, the file facts carry `all_exports` and `all_literal`, and the reply states
`interface_boundary: Supported`. Python uses the same seam. No second path exists.

**Facts.** In the linked reply only (the subprocess reply stays the frozen survey of the phase
`imports`, so the golden replies do not change):

- `reexport_chain` of each import that names a symbol: the hops `module.name`, first the imported
  name, then each proven re-export (`ir/reexports.py`, `resolve_reexports`). It is written by
  `survey/routes.rs`.
- `profile_limits`: `interface_boundary: Supported` and `dependency_symbols: Supported`, bound to
  the resolution feature `import-routes-v1` (the store refuses a statement without it, as it binds
  the TypeScript statement to `script-globals-v1`). Only the Python profile may state
  `interface_boundary` for an import survey; Dart keeps `Unsupported`.

**What proves the receipt.** `interface::receipt` is unchanged: each selected crossing must give a
verdict (`assess`), and `Scope::complete` consumes the receipt with the ownership, coverage and
gap proofs. A PASS needs `ScopeComplete`; the survey adds none. The model gives a verdict only when
the route holds the first hop `module.name`; an empty route is the named gap "unproven publication
route".

**Forms that withhold the route (each is a named gap, never a verdict).**

| Unseen form | What the survey does |
|---|---|
| `__all__` named but not one literal list of strings (dynamic, `+`, `+=`, `.append`, a second assignment, imported) in a hop module | route withheld |
| a re-exported binding that is not unique in its module (`stable_bindings`: a second import, a `def`, an assignment, a star import) | route withheld |
| an alias with two targets, a cycle, a candidate re-export (`reexport_candidate`) | route withheld |
| a star import `from m import *`, a module object (`import m`, `from p import sub`) | no symbol route (`UnreadBinding`, or a module verdict) |
| an overload group, a re-export through `globals()`, `exec` or a class body | not proven by this survey (4.0.1 proves overloads): route withheld |
| an import under `TYPE_CHECKING` whose route has more than two hops | `TypePublication` gap (unchanged) |

**Coverage of a route.** `interface::assess` follows 4.0.1 `interface_covers_import`: the import
is public when any hop is public (`module:name`, or a public module whose literal `__all__` holds
the name or that has none). A route under `TYPE_CHECKING` keeps its first hop only, so TypeScript
named-type routes (one or two hops) are decided as before.

**4.0.1 source of truth.**

| Check | 4.0.1 |
|---|---|
| verdict of one import | `check/evaluation/rules.py:_interface_verdict`, `ir/model.py:interface_covers_import`, `facade_covers` |
| route and origin | `ir/reexports.py:resolve_reexports`, `analyzer/python/imports.py` |
| `__all__` names | `analyzer/python/binders` (`literal_all_exports`, `all_is_one_literal`) |

**4.0.1 false verdicts and what the core does.** The core is never less strict:

| 4.0.1 form | 4.0.1 | Core |
|---|---|---|
| `__all__ = compute()`: unreadable `__all__` read as none, every name passes | PASS (false) | UNKNOWN |
| `__all__ = ['f'] + more()`: the literal part is the whole list | PASS (false) | UNKNOWN |
| `__all__ = ['f']` then `__all__ += ['g']` | PASS | UNKNOWN |
| binding with two sources | PASS | UNKNOWN |
| a route through a proven re-export, covered at the second hop | PASS | PASS |
| the folded rule gaps of #619 (`catalog_argument`, `boundary_types`, `forbidden_effect_under_condition`) | not this rule | unchanged: UNKNOWN `rule_kind_not_ported` |

`tests/test_cli_python_interface.py` runs 20 plants; the verdict of 4.0.1 for each is recorded in
`tests/python_interface_plants.py` (one `report` of the read-only oracle for each plant).

**Not in this change.** The hygiene checks `interface.undeclared`, `unused`, `usage_unknown`,
`missing` and `planned_built` stay `contract_hygiene_not_ported`, so a Python contract with an
`interface_boundary` rule still gives a run UNKNOWN, with the rule rows decided.
