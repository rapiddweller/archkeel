# AD-894 A plain statement is no import door in the Python survey

Status. Accepted. It amends AD-450 (the door and import-state sites) and AD-574 (inert reads).

The Python survey gave `dynamic_import` or `import_system_change` for three statements that are
no import. Each gap marks the whole run as unproven, so a clean project got a wrong UNKNOWN.

1. `inspect(1)`, where the module defines `def inspect`. The name `inspect` is above the door
   `inspect.getmodule`, and the survey read it as the standard module.
2. `Plan.code`, where `Plan` is a class of the scan that `from app.beta.models import Plan` binds.
   The survey took each imported name as a possible module, so `.code` read as the `code` module.
3. `[p for p in sys.path if p]`. Each reference to `sys.path` was an import-system change.

## Decision

- A name that one plain `def` or `class` of the module body binds, and that no import binds, is
  local. It is no door module. The survey drops the site after the walk, by its range
  (`reflect::Proved`). The builtin doors (`eval`, `exec`) and the import functions stay doors,
  also when the module defines them.
- An imported name is a class of the scan when each origin is `module.Class` of a module of the
  scan, one plain `class` binds `Class` there, and the importing module binds the name one time.
  The attribute `code` of such a name is no `code` module.
- A read of `sys.path` gives no gap in these positions: the source of a `for` or of a comprehension,
  and the value of a subscript read. Each other use is a gap, so a
  call, an assignment, an augmented assignment, a subscript store, `del`, a call of a method and
  an alias (`p = sys.path`) keep the gap.

## Rejected

- Drop `inspect` and `code` from the door list. `import code; code.interact()` is a true site.
- Treat each read of `sys.path` as inert. A call such as `f(sys.path)` can change it.
- Treat comparisons as inert. An operand can receive `sys.path` in its comparison method and change it.
- Resolve a class through a package re-export. That needs the binding proof of `routes.rs`.

## Kept gaps

- A class that a package re-exports (`from app import Plan`) keeps the gap on `Plan.code`.
- `from sys import path` and `sys.path` as a plain value keep the gap.
- Comparisons keep the gap, including literal membership tests, until a proof covers their operands.
- A `def` that another statement of the module also binds keeps the gap.

## Tests

`native/python/src/survey/hazards_proved_tests.rs`: each false site and each true site that looks like it, with
`sys.path` writes, `code.interact`, `importlib.import_module` and a standard `inspect` module.

Undo: remove `reflect::Proved` and `reflect::proved`, and their use in `hazards::split`.
