# AD-64 `archkeel.api` is the declared external contract, and `ir` performs no I/O

A new component, `api` (`src/archkeel/api.py`, packages `["archkeel.api"]`), is the one
declared external read surface: its `__all__` is `ViolationRow`, `load_observation` and
`violation_rows`, nothing else, and `docs/reference.md`'s "Reading a report's violations"
section documents exactly those three names, checked against `archkeel.api.__all__` by
`tests/test_violations.py::test_api_all_matches_the_names_reference_md_documents` so the prose
and the module cannot drift. `load_observation`'s file read moves out of `ir.codec` into
`archkeel.api.load_observation`, which reads the path and hands the bytes to `ir.codec`'s
`decode_json`, `decode_canonical_model` and `parse_observation` unchanged; `ir.codec` no longer
performs I/O. `archkeel.ir.codec.load_observation` (AD-54) is removed outright, not deprecated:
this repository is at 0.4.x and the surface was days old, so there is one supported way in, not
a compatibility shim carrying two. `COMP-API`'s `requires` entry names `ir`, `through`
`archkeel.ir.baseline`, `archkeel.ir.codec` and `archkeel.ir.model` (AD-42), the three modules
the facade actually imports; that crossing pushes `ir.baseline`'s own public names used across a
component boundary past `init`'s half-of-names threshold (AD-9), so `draft_contract` now
proposes the whole module, `"archkeel.ir.baseline"`, in place of the four symbol entries AD-54
drafted - the committed contract follows that draft exactly, as it already did before this
change, rather than being hand-edited into a shape the draft disagrees with.

`ir/digest.py`'s `package_digest` keeps reading files, and this decision does not move it. It
hashes Archkeel's own installed source to identify the running checker, consumed by
`check/validation.py`'s provenance and never exposed through `archkeel.api`; it is not a
derivation over evidence a consumer supplies, the concern this decision and AD-17 actually name.
AD-17's "no I/O" was already read narrowly, no I/O in a *derivation* over already-read evidence,
not a blanket rule; `package_digest` sits outside that reading exactly as it did before, so it
needed no new argument to stay, only this sentence saying so instead of leaving it unmentioned
now that the question has been raised.

Reason: issue #46 - AD-54 declared a supported reading path out of two internal modules that
only the documentation called supported: `archkeel/__init__.py` was empty, so nothing in the
repository stated which names had to survive an `ir.codec` restructuring, in a tool whose whole
argument is that an interface should be declared where a check can hold it. `load_observation`
also put a file read inside `ir`, whose own component responsibility is I/O-free derivations
(AD-17); AD-54's "`ir/digest.py` already does this" was a weak defense of that, an existing
boundary leak, not a reason to add a second one.

Rejected: putting the facade in `archkeel/__init__.py` itself, the module the issue's own
suggestion left open. `complete_assignment`'s check (`_assignment_violations`) skips a module
whose qualified name equals the scan namespace unconditionally, "archkeel" itself, not only when
it is blank; whatever that module imported would stay assigned to no component, so
`component_for` would return `None` for it, and `requires_violations` skips a crossing whose
source has no owning component. A facade living there would import `ir` across a boundary that
`complete_requires` could never see - the one check this decision exists to hold. `archkeel.api`
as its own top-level module is what `draft_contract` already groups as a component on its own
(every module directly under the namespace becomes one, SKILL.md's "one component per top-level
subpackage/module"), so it is also what stays reproducible by `init`'s own draft, not a hand
carve-out. Rejected: leaving `ViolationRow`/`violation_rows` importable only from `ir.baseline`
with no facade module, because that leaves the external promise exactly where AD-54 found it, in
prose the `public` list AD-9 governs does not cover. Rejected: a compatibility shim re-exporting
`load_observation` from `ir.codec`, because a 0.4.x repository days into having the surface owes
no deprecation window, and a shim only makes "two supported ways in" literal instead of retiring
it.

Limit: `archkeel.api.__all__` is the whole external promise - the columnar file format
`decode_canonical_model` inflates and every other `ir` internal, `ir.baseline` and `ir.codec`
included, stay unpromised even where AD-9's `public` list marks them whole-module for Archkeel's
own cross-component use, a narrower and separate control (AD-54's own Limit already said as
much; this one narrows it further, to `archkeel.api` alone, now that a facade exists to name).
`ir/digest.py` is untouched, for the reason above. `archkeel.ir.codec.load_observation` is gone,
not aliased: a caller against the pre-AD-64 import path gets `ImportError`. Check:
`tests/test_violations.py`'s `test_load_observation_reads_the_canonical_report_bytes_back`,
`test_reference_md_snippet_reads_a_report_and_lists_its_rows`,
`test_api_all_matches_the_names_reference_md_documents`,
`test_old_ir_codec_import_path_is_gone` and `test_ir_codec_no_longer_reads_a_file`, all against
the `tour` demo variant (AD-11) except the last two; `tests/test_self.py`'s
`test_self_contract_public_matches_drafted_proposal` against the corrected `ir.baseline` and new
`COMP-API` entries, and `test_self_contract_closes_every_component_pair`; and
`archkeel validate --root . --json` on Archkeel's own contract.
