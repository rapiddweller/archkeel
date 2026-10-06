# AD-71 A promised name is checked against the module's own `__all__`

## What changes

`public_api_diagnostics` checks symbol entries against a module's literal `__all__`,
when present, instead of module existence alone.

| Entry | Module scanned | Module's `__all__` | Verdict |
|---|---|---|---|
| `archkeel.api:load_violations` | yes | contains it | fine |
| `archkeel.api:Typo` | yes | does not contain it | `api_surface.missing` |
| `sample.core:WIDGET_LIMIT` | yes | none declared | fine, unchecked |
| `sample.gone:Widget` | no | -- | `api_surface.missing`, as before (AD-66) |

## Why

A scanned module does not prove its promised name exists. Literal `__all__` supplies
export-surface evidence. Symbols alone omit constants and aliases
([AD-56](ad-56-a-public-entry-the-scan-never-saw-is-missing-and-planned.md)).

## Rejected

Symbol lookup would misreport constants and aliases. UNKNOWN for missing `__all__`
would add noise to an architect-written declaration. Extending component public
checks would silently change a different contract boundary.

## Limit

Without literal `__all__`, retain module-only checking: `sample.core:Typo` remains
unchecked. Self API's three names are fully checked. Equivalent component-public
validation remained open.

## Check

Validation tests cover names absent from `__all__` and unchanged module-only
checking without it.
