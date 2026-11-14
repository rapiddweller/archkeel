# AD-514 The core proves a use of a public entry from imports and names the rest

**Status.** Proposed. Part of #880. It follows AD-504 and replaces the named gap
`contract_hygiene_not_ported` for the family `interface.*` (AD-466).

**Reason.** A Python contract with an `interface_boundary` rule was UNKNOWN for each run: the five
checks `interface.undeclared`, `unused`, `usage_unknown`, `missing` and `planned_built` were not
ported. Release 4.0.1 refuses the contract (exit 2) for each finding. M-review-workflow passes on
4.0.1 (12 PASS, exit 0) and held UNKNOWN on the core only for this family.

**What 4.0.1 reads (`check/validation/public_api.py`, `inside.py`).** An entry is *used* when a name
of an import route reaches it (`_entry_reached_by`), when an import names its module without
symbols, or when a declared facade signature exposes the type it names (`facade_types`). A finding
is then: no `public` entry but imports received (`undeclared`); an entry that nothing reaches
(`unused`, or `missing` when its module was not scanned, `usage_unknown` when an unproven route may
reach it); a scanned `planned` entry that something reaches (`planned_built`). A mounted contract
also counts imports from outside its domain when each boundary publishes them.

**Decision.** The core reads the imports and no declared signature, so it proves a use and never an
absence of use (`hygiene_interface.rs`, one function for the root and for each mount):

| Finding of the core | When | 4.0.1 gives |
|---|---|---|
| `interface.undeclared` | a component receives imports from another component and has no `public` | `interface.undeclared` |
| `interface.usage_unknown` | a `public` entry that no proven import reaches | `interface.unused` or `interface.missing`, or nothing when a signature reaches it |
| `interface.planned_built` | a scanned `planned` entry that a proven import reaches | `interface.planned_built` |
| `interface.usage_unknown` | a scanned `planned` entry that no import reaches | nothing, or `planned_built` through a signature |
| none | each public entry reached by a proven import; no planned entry scanned or reached | nothing |

Each finding is a named hygiene row and holds back a PASS. The run can PASS only when every
`public` entry has a proven use. The core never clears a contract that 4.0.1 refuses.

**What counts as a use.** A proven import route of AD-504 (`reexport_chain`, any hop; an empty
route reaches nothing), or a module import without symbols. A star import names no symbol, so it
reaches no `module:name` entry (4.0.1 does the same). For a mount, an import from outside its
domain counts when the component that holds the mount publishes it at the root
(`_import_published_through_ancestors`): the root owns the source, the parent owns the target, and
the parent's `public` covers the imported name, and then the target's `public` or `planned` covers
it. A deeper mount counts local imports only, so it can only give more `usage_unknown` rows.

**4.0.1 false verdicts and what the core does.**

| 4.0.1 form | 4.0.1 | Core |
|---|---|---|
| entry reached only by a declared facade signature | clear | `interface.usage_unknown` |
| planned scanned entry reached only by a signature | clear | `interface.usage_unknown` |
| a route through an unproven re-export (candidate) | `interface.usage_unknown` or clear | the route is empty, so `interface.usage_unknown` |

`tests/test_cli_python_lifecycle.py` runs 12 plants and 4 variants of M-review-workflow; the
verdict of 4.0.1 for each is recorded in `tests/python_lifecycle_plants.py` and
`tests/python_lifecycle_mounts.py` (one `validate` of an installed 4.0.1 for each).

**Not in this change.** `declarations.public_api` (`api_surface.missing`) and the inside
`allowed_dependency` check keep their named gaps. The facade signatures need the `symbols` section
of the Python survey, which the survey does not write.
