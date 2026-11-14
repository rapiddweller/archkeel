# AD-504 The Python survey writes the publication route of each named import

**Status.** Proposed. Part of #880. It amends AD-450 (the survey states no interface) and AD-500.
The hygiene checks `interface.*` follow in AD-514.

**Reason.** `interface_boundary` on Python was UNKNOWN for each rule: the linked survey stated
`interface_boundary: Unsupported`. Release 4.0.1 decides it (M-review-workflow: 12 PASS). The core
decides this rule for TypeScript from one seam: import records with `symbol` and `reexport_chain`,
file facts with `all_exports` and `all_literal`, and the statement `interface_boundary: Supported`.
Python uses the same seam; `model`, `eval`, `core` and `report` name no language.

**Facts.** In the linked reply only (the subprocess reply stays the frozen survey, so the golden
replies do not change): `reexport_chain` of each named import (`survey/routes.rs`, a port of
`ir/reexports.py`), and `interface_boundary` and `dependency_symbols` stated `Supported`. The store
binds both statements to the resolution feature `import-routes-v1`, as it binds the TypeScript
statement to `script-globals-v1`. Dart may not state an interface.

**Truth.** A route is what Python binds when the modules run. A route that the survey cannot make
complete stays empty: the model then gives the named gap "unproven publication route", never a
verdict. PASS needs `ScopeComplete` as before. `survey/bound.rs` is the one function of the names
that a module body may bind (the module scope at any depth, each target form, walrus, `del`,
`global`); the package shadow rule and the proof of a re-export both read it.

**Forms that withhold a route (named gap, never a verdict).**

| Form | Rule |
|---|---|
| `__all__` named but not one literal list (`+`, `+=`, `.append`, second assignment, import) | route withheld |
| a re-export that is not the one plain statement binding its name: an import in a function, a class body, `if`, `try`; a second binder (`def`, assignment, `for`, `with`, walrus, `del`, `global`, star import) | route withheld |
| an alias with two targets, a cycle, a candidate re-export | route withheld |
| a package body that binds the name in any form (the name may be the attribute or the submodule) | route withheld |
| a write to a module of the scan from another module (`lib.f = x`, `+=`, `del`, `setattr`, a mutation or store on `lib.__all__` or `lib.__dict__`, `vars(lib)`; the base is an import in any scope, a dotted path, a literal `import_module`, or an imported name of unknown kind) | each route through the module withheld (`writes.rs`) |
| a guarded (`TYPE_CHECKING`) import that passes a re-export | route withheld: the model reads the first hop of a guarded import (the TypeScript type rule) |
| a star import, a module object, an overload group, `globals()` or `exec` re-export | no symbol route, or withheld |

**Coverage.** `interface::assess` follows 4.0.1 `interface_covers_import`: public if any hop is
public. A name that starts with `_` is not public at any hop, also when `__all__` lists it or an
exact entry names it; a port `app.lib:mod` met by `from app.lib import mod` fails in 4.0.1 and in the
core; 4.0.1 passes none of these, so nothing is fixed (plants in `python_interface_plants.py`).

**Open false PASS, not accepted.** The core gives PASS where the truth is FAIL, as 4.0.1 does:
`import app.lib` then `app.lib._priv.secret()` with public `app.lib` (the rule judges imports; a use
through a public module object is no import), and a write from a C extension or through `globals()`
of another module. Each is pinned as such (`open_pass`) and listed in `docs/known-limits.md`.
`sys.modules` and a computed `import_module` are survey gaps (AD-450): UNKNOWN.

**4.0.1 false verdicts.** `__all__ = compute()` and `['f'] + more()` pass every name in 4.0.1: UNKNOWN
in the core. A re-export through a function, a class, `try`, a shadowed submodule or a write from
another module passes in 4.0.1: UNKNOWN in the core. `tests/test_cli_python_interface.py` runs 48
plants; `Plant.four` is the verdict of an installed 4.0.1 for each.
