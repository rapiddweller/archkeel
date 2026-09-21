# AD-66 `declarations.public_api` names a consumer outside the package

AD-9's `public` names one component's promise to another component of the *same* package,
policed at every crossing by `interface_boundary`. `declarations.public_api` names a different
thing this repository already had a field for: the surface a consumer *outside* the package may
rely on, the case AD-9 had no need to distinguish until AD-64 gave Archkeel itself such a
surface, `archkeel.api`. Before this decision `public_api` was already parsed
(`ir.codec.parse_contract`), typed (`ir.model.ContractDeclarations.public_api`), projected into
every observation as a `declared_public_api` evidence item under `area="api_surface"`
(`analyzer.embedded.contract`), and checked for two things every declaration gets: its name must
resolve inside the configured namespace (`reference.namespace`) and its provenance file must
exist (`reference.provenance`). None of that machinery was inert, and none of it checked that the
name it declared existed, or connected it to Archkeel's own external promise: `archkeel.api`'s
`__all__` and `docs/reference.md`'s prose only agreed with each other, held together by
`tests/test_violations.py::test_api_all_matches_the_names_reference_md_documents` comparing one
hard-coded set against the other, neither read from `architecture-contract.json`.

Archkeel now declares its own `public_api`:

```json
"public_api": [
  "archkeel.api:ViolationRow",
  "archkeel.api:load_observation",
  "archkeel.api:violation_rows"
]
```

and `test_api_all_matches_the_names_reference_md_documents` reads `declarations.public_api` from
`architecture-contract.json` and checks `archkeel.api.__all__` and the reference-doc names each
against it, not against each other: a fourth export or a dropped one now shows up as a contract
disagreement, checked the same way every other value this repository promises is.

`validate` gains one new existence check, `api_surface.missing`, `public_api_diagnostics` in
`check/validation.py`: a `public_api` entry whose module the scan never saw is a typo or a
promise the package has not built yet, the same fact `interface.missing` already reports for a
`public` entry the scan never saw (AD-56). It reuses `_entry_module` and `_scanned_modules`
unchanged, so a `pkg.module:Name` entry is judged by its module alone, for the reason AD-56 gave:
`symbols` records only classes and functions, so an unmatched name there would as easily be a
constant or a `TypeAlias` as a genuine typo. There is no `interface.unused` twin: `interface.unused`
exists because `interface_boundary` can see every crossing that could use a `public` entry, so
silence is evidence; nothing inside the scan crosses into `public_api` the way one component
imports another; a consumer outside the package is not observed, so its silence proves nothing.
Ownership and underscore checks (`reference.public_owner`, `reference.public_underscore`) stay
`public`/`planned`-only: those exist because a `public` entry is one component's promise, so
another component's module claiming it is a contradiction the contract can catch; `public_api`
belongs to no component, so there is nothing for an entry to be owned by.

Reason: issue #58 — the three names that are Archkeel's own external promise lived in `api.py`'s
`__all__` and in `docs/reference.md`'s prose, kept in step only by a test holding two documents
against each other, exactly the drift a contract-first tool exists to prevent everywhere else.
AD-9 already read as though `public_api` had nothing left to say once `public` existed
("`declarations.public_api` stays valid but is superseded"); AD-64 made that reading wrong by
giving Archkeel a package boundary `public` cannot describe, one crossed by a consumer no scan
observes.

Rejected: inventing a new field for an external surface, the shape the issue itself warned
against. `declarations.public_api` and `declarations.public_api_provenance` were already in the
schema and the model, parsed, projected and reported; the gap was that nothing read them back
against the module they name or against `archkeel.api` itself, not that the field was the wrong
one. Rejected: checking a `public_api` entry's `:Name` half against `symbols`, for the same
reason AD-56 rejected it for `public` — it would misreport a module-level constant or a
`TypeAlias` as missing forever. Rejected: holding `public_api` to the same ownership check as
`public` (`reference.public_owner`), because that check asks whether *another component* may
claim a name, a question that presupposes the crossing is between two components of this
package; a `public_api` entry has no such other side within the scan to contradict it. Rejected:
declaring `public_api` unused when no `archkeel.api`-shaped module imports it, mirroring
`interface.unused` — the analyzer only sees this package, never the consumers `public_api`
promises to, so absence of an internal crossing is not evidence of anything.

Limit: `api_surface.missing` reads `modules` alone, the same blind spot `interface.missing`
carries for the same reason: a `pkg.module:Name` entry whose module exists but whose name does
not is not caught. Nothing checks that a `public_api` entry's actual Python object still matches
what a consumer last saw, only that the module exists; `public_api_provenance`'s file-exists
check (`reference.provenance`) and the namespace check (`reference.namespace`) are unchanged and
apply exactly as before AD-64. `public_api` remains under `declarations`: Class C's "Archkeel
makes no claim that code follows a declaration" (`docs/rules.md`) still describes it — existence
is a much narrower claim than that a consumer actually reaches the name, or that the name's
signature has not changed — so it is not promoted to Class A. Check:
`tests/test_validation.py::test_missing_public_api_entry_is_a_diagnostic`,
`test_built_public_api_entry_has_no_diagnostic`,
`tests/test_violations.py::test_api_all_matches_the_names_reference_md_documents`,
`fixtures/demo_catalog_validation.py`'s `validation-api-surface-missing` row, run by
`tests/test_architecture_demo.py::test_variant_produces_the_catalogued_findings`; and
`archkeel validate --root . --json` on Archkeel's own contract, which now declares `public_api`.
