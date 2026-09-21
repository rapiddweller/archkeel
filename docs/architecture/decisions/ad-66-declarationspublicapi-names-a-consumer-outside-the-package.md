# AD-66 `declarations.public_api` names a consumer outside the package

## What changes

Two declarations, two questions:

| Declaration | Whose promise, to whom |
|---|---|
| `component.public` | one component's, to another component of the same package |
| `declarations.public_api` | the package's, to a consumer outside it |

`public_api` was already parsed, typed, projected and namespace-checked. Nothing read it back
against the module it names, and nothing connected it to Archkeel's own promise: `api.py`'s
`__all__` and `docs/reference.md` agreed only with each other, held by a test comparing two
hard-coded sets.

Archkeel now declares its own, `validate` gains `api_surface.missing` for an entry whose module
the scan never saw, and the `__all__`/reference test reads the contract instead of itself.

## Why

[AD-9](ad-09-components-declare-their-interface.md) read as though `public_api` had nothing left
to say once `public` existed. [AD-64](ad-64-archkeelapi-is-the-declared-external-contract-and-ir.md)
made that wrong by giving Archkeel a package boundary `public` cannot describe: one crossed by a
consumer no scan observes.

That is also why there is no `interface.unused` twin here. `interface.unused` works because
`interface_boundary` sees every crossing that could use a `public` entry, so silence is
evidence. Nothing inside the scan crosses into `public_api`; a consumer outside is not observed,
and its silence proves nothing.

Ownership and underscore checks stay `public`-only for the same reason: they ask whether another
component may claim a name, and a `public_api` entry has no other side within the scan.

## Rejected

| Alternative | Why not |
|---|---|
| Invent a new field for the external surface | It already existed, parsed and projected; the gap was that nothing read it back. |
| Hold `public_api` to `reference.public_owner` | That check presupposes two components of this package on either side of the crossing. |
| Report an unused `public_api` entry | The analyzer never sees the consumers it promises to. |

## Limit

Existence is a narrower claim than that a consumer reaches the name, so `public_api` stays a
Class C declaration. This decision checked the module alone; the name itself is checked by
[AD-71](ad-71-a-promised-name-is-checked-against-the-modules-own-all.md) and the types it hands
out by [AD-73](ad-73-the-external-surface-is-judged-by-the-same-walk.md). The three names it
first declared were replaced by the single `load_violations` call in
[AD-70](ad-70-the-external-promise-declares-every-type-it-hands-out.md).

## Check

`tests/test_validation.py::test_missing_public_api_entry_is_a_diagnostic` and
`test_built_public_api_entry_has_no_diagnostic`;
`tests/test_violations.py::test_api_all_matches_the_names_reference_md_documents` reading the
contract; the `validation-api-surface-missing` catalog row; and `archkeel validate --root .`
on Archkeel's own contract.
