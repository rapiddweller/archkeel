# AD-66 `declarations.public_api` names a consumer outside the package

## What changes

| Declaration | Whose promise, to whom |
|---|---|
| `component.public` | one component's, to another component of the same package |
| `declarations.public_api` | the package's, to a consumer outside it |

Reuse the parsed, typed and projected `public_api`. Declare Archkeel's external
surface; `validate` reports `api_surface.missing` for an unscanned module.
The `__all__`/reference test reads the contract instead of hard-coded sets.

## Why

[AD-64](ad-64-archkeelapi-is-the-declared-external-contract-and-ir.md)'s external promise
needs a package boundary beyond [AD-9](ad-09-components-declare-their-interface.md)'s
component interfaces. Outside consumers are unobserved, so no unused-entry finding
can follow from their silence. Ownership and underscore checks remain public-only:
they concern the other component within a scan.

## Rejected

A new field would duplicate the existing one. Public ownership and usage checks
cannot prove anything about unobserved external consumers.

## Limit

This Class C declaration initially checked only module existence.
[AD-71](ad-71-a-promised-name-is-checked-against-the-modules-own-all.md) checks names;
[AD-73](ad-73-the-external-surface-is-judged-by-the-same-walk.md) checks exposed types.
[AD-70](ad-70-the-external-promise-declares-every-type-it-hands-out.md) replaces the
initial three names with `load_violations`.

## Check

Validation tests cover missing and built API modules; violation tests compare
contract, exports and reference docs; `validation-api-surface-missing` demonstrates
the finding. Self validation checks the declaration.
