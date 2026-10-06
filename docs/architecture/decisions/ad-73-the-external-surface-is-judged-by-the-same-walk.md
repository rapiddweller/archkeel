# AD-73 The external surface is judged by the same walk

## What changes

The analyzer records types exposed by `declarations.public_api`; `check` compares
resolved exposures with resolved declarations without doing name resolution.

| Entry's signature | Before | Now |
|---|---|---|
| `-> UndeclaredType` | silent | `api_surface.missing` |
| `(x: UndeclaredType)` | silent | `api_surface.missing` |
| `Row.field: UndeclaredType` | silent | `api_surface.missing` |
| `-> tuple[UndeclaredType, ...]` | silent | `api_surface.missing` |
| `-> Path`, `-> tuple[Declared, ...]` | silent | silent |

## Why

[AD-70](ad-70-the-external-promise-declares-every-type-it-hands-out.md)'s three-name test
could not enforce arbitrary future exposures. Reuse `_boundary_type_verdict`'s
walk ([AD-69](ad-69-one-annotation-is-read-once-for-both-readers.md)); direct bare-name
resolution had missed removal of `ViolationRow` while a tuple return still exposed it.
Resolve declaration origins too, so re-exported API types match their defining modules.

## Rejected

Resolution in `check` violates its analyzer boundary and duplicates annotation
knowledge. Internal `api.public` entries would be unused by unobserved outside
consumers (AD-66). Literal declared-string comparison misses re-export identity.
Unscanned library types are not a scanned package's own undeclared promise.

## Limit

Classes contribute only annotated class-body fields, not `__init__` assignments.
Unions, mappings, nested subscripts, dotted names and forward references inherit
AD-67's uncertainty. Internal and external readers share those limits.

## Check

`tests/test_public_api_boundary.py` covers returns, parameters, fields, builtins
and declared collections. Self tests enforce the API promise; structural analyzer
tests reject a second name-resolution reader.
