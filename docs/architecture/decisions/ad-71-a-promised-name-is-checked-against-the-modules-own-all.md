# AD-71 A promised name is checked against the module's own `__all__`

## What changes

`public_api_diagnostics` judged a `module:Name` entry by its module alone. It now also reads
that module's literal `__all__` when it declares one:

| Entry | Module scanned | Module's `__all__` | Verdict |
|---|---|---|---|
| `archkeel.api:load_violations` | yes | contains it | fine |
| `archkeel.api:Typo` | yes | does not contain it | `api_surface.missing` |
| `sample.core:WIDGET_LIMIT` | yes | none declared | fine, unchecked |
| `sample.gone:Widget` | no | -- | `api_surface.missing`, as before (AD-66) |

## Why

A consumer imports the promised name, not its module. `from archkeel.api import Typo` fails at
import time, and the contract called that promise kept because `archkeel.api` exists.

A module that declares `__all__` states its own surface, so a name outside it is *proven*
absent -- no guessing from what the scan happened to record. That is the difference from the
component `public` list, whose sibling check
([AD-56](ad-56-a-public-entry-the-scan-never-saw-is-missing-and-planned.md)) judges by module
alone because `symbols` records only classes and functions and would report a constant or a
type alias as missing. Here the module itself supplies the answer, and where it does not, the
old reading stands unchanged.

## Rejected

| Alternative | Why not |
|---|---|
| Check the name against `symbols` | Misreports every constant and type alias, the reason AD-56 checks the module only. |
| Report UNKNOWN for a module without `__all__` | An undecidable position in a list an architect writes by hand is noise, not a finding; the module-only reading already covers the typo that matters. |
| Extend the same check to component `public` | Different question, different evidence, and a silent behaviour change for every contract in the wild. |

## Limit

A module without `__all__` keeps AD-66's module-only reading, so `archkeel.api:Typo` is caught
and `sample.core:Typo` is not. Archkeel's own surface declares `__all__`, so its three entries
are fully checked. Whether component `public` should gain the same check stays open.

## Check

`tests/test_validation.py::test_public_api_name_outside_declared_all_is_missing` fails without
the change: the module is scanned, so the entry passed. Its twin,
`test_public_api_name_is_unchecked_without_declared_all`, pins that a module declaring no
`__all__` is still judged by its module alone.
