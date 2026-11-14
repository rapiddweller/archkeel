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

**Truth.** A route is what Python binds when the modules run, not what a statement says. A route
that the survey cannot make complete stays empty: the model then gives the named gap "unproven
publication route", never a verdict. `survey/bound.rs` is the one function of the names that a
module body may bind (each statement of the module scope at any depth, every target form, walrus,
`del`, `global`); the package shadow rule and the proof of a re-export both read it.

**Forms that withhold the route (each is a named gap, never a verdict).**

| Unseen form | What the survey does |
|---|---|
| `__all__` named but not one literal list of strings (dynamic, `+`, `+=`, `.append`, a second assignment, imported) in a hop module | route withheld |
| a re-export that is not the one plain statement binding its name in its module: an import in a function, a class body, `if`, `try`; a second binder (`def`, assignment, `for`, `with`, walrus, `del`, `global` in a function, star import) | route withheld (`routes.rs::link` reads `bound.rs`) |
| an alias with two targets, a cycle, a candidate re-export (`reexport_candidate`) | route withheld |
| a package body that binds the name in any form, so that `from pkg import name` may be the attribute or the submodule | route withheld (the import is `ambiguous`) |
| a write to a module of the scan from another module: `lib.f = x`, `lib.f += 1`, `del lib.f`, `setattr(lib, ...)`, a mutating call or a store on `lib.__all__` or `lib.__dict__`, `vars(lib)[...]`; the base is a name bound by an import in any scope, a dotted path, a literal `import_module` call, or an imported name of unknown kind (it names the module it came from) | every route through that module withheld (`writes.rs`) |
| an import under `TYPE_CHECKING` whose route passes a re-export | route withheld: the model reads the first hop of a guarded import only (the TypeScript type rule), so the Python collector writes no longer route |
| a star import `from m import *`, a module object (`import m`, `from p import sub`) | no symbol route (`UnreadBinding`, or a module verdict) |
| an overload group, a re-export through `globals()`, `exec` or a class body | not proven by this survey: route withheld |
| an import under `TYPE_CHECKING` of a module object or a route of more than two hops | `TypePublication` gap |

**Open false PASS, not accepted.** The core still gives PASS where the truth is FAIL for the forms
below. 4.0.1 gives PASS for each. Each has a plant pinned as such (`open_pass` in
`tests/python_interface_plants.py`); a fix removes the pin.

| Form | Why the survey does not see it |
|---|---|
| `import app.lib` then `app.lib._priv.secret()` with public `app.lib` | the rule judges imports; a use of a private module through a public module object is no import. If the rule text means "no use of a private module", the core is wrong here and 4.0.1 was wrong before it |
| a write from a C extension, or a write through `globals()` of another module | no statement of the scan names the module |

A write through `sys.modules[...]` and a computed `importlib.import_module(name)` are survey gaps
(AD-450), so the rule is UNKNOWN (plant "open: write through sys.modules" pins that).

**Coverage of a route.** `interface::assess` follows 4.0.1 `interface_covers_import`: the import
is public when any hop is public (`module:name`, or a public module whose literal `__all__` holds
the name or that has none). A route under `TYPE_CHECKING` keeps its first hop only, so TypeScript
named-type routes (one or two hops) are decided as before; Python writes no guarded route of more
than one hop, so the first hop is the whole route.

**Names that 4.0.1 and the core fail alike** (plants `private name listed in __all__`, `exact entry
of a private name`, `dunder name`, `port that names a submodule`): a name that starts with `_` is
not public at any hop, also when `__all__` lists it or a `module:name` entry names it; a port
`app.lib:mod` met by `from app.lib import mod` (a submodule, no symbol) is FAIL in 4.0.1 and in the
core. 4.0.1 gives PASS for none of them, so nothing is fixed.

**Store binding.** The store accepts `interface_boundary: Supported` for the Python survey only with
the feature `import-routes-v1` (and so `dependency_symbols: Supported`).

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
