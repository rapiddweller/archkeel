# AD-43 A candidate declares what it changed, not what the scanner counted or what every module already carries

Two cuts land together because both come from the same measurement.
First, the eight per-counter `coverage` records (`files_discovered`, `calls_resolved`, and the
rest) stop feeding `_compare_records`; `_delta_records` returns `()` for the `coverage`
dimension instead of calling the record-projection machinery, so `_coverage_records` and its
`Projection`/`EvidenceClass` plumbing are gone. `DeltaCoverage` already reads
`baseline.coverage.status`/`head.coverage.status` into one PASS/FAIL, and both full `Coverage`
records stay on the observations `report` renders from, so nothing a reviewer could read is
lost, only five mechanical `semantic_changes` entries that shifted by construction whenever any
file was added or removed. Second, `check/python_profile.py`'s `crossing_imports`, the one
function `delta.py` and `ratchets.py` both call to turn raw `imports` records into crossings,
drops `from __future__ import annotations` before it reaches either caller: a
`_LANGUAGE_BOILERPLATE_IMPORTS` set of `(target_module, symbol)` pairs, one entry today, marks
imports that name no project symbol on either side and that every module in a namespace already
carries. `ratchets.py`'s `private_crossings` scalar is untouched, because `annotations` is never
a private symbol. Reason: adding `src/archkeel/ir/labels.py`, two lines,
`from .digest import package_digest` and one function, on top of Archkeel's own accepted
observation measured 7 `semantic_changes` for a change with one informative fact, one
`dependency_edges` addition; the other six were the five coverage counters and the future
import, none of which said anything about `labels.py` itself (roadmap item 6). Rejected: emitting
one semantic change per `coverage` dimension only when its aggregate `status` flips, instead of
none at all, was rejected because `DeltaCoverage.status` already carries exactly that flip as a
typed field `evaluate_expectation` reads unconditionally, so a tenth declarable entry saying the
same thing would cost an agent a declaration for information the check already enforces without
one. Filtering `from __future__ import annotations` in the analyzer's `imports.py` collector
instead of in the checker's own profile was rejected because that is a fact about what the
source imports, true regardless of who reads it, and [AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md) ties any change to what the analyzer
records to `ANALYZER_VERSION`; every other reader of the `imports` section (`ratchets.py`, the
HTML report's component flow, `tools/interface_profile.py`) still needs the record, so only the
one place that turns a record into a declarable crossing should stop counting this one. Neither
cut touches the analyzer, so `ANALYZER_VERSION` is unchanged; `DELTA_SCHEMA_VERSION` rises to
1.3.0, because the same two observations now produce fewer `semantic_changes` than an older
checker would compute for them, and [AD-8](ad-08-statement-constructs-are-class-a-rules.md)'s fail-closed reading of a schema version is for a
reader that does not yet know a meaning changed, not only for one that would otherwise accept
something invalid. `EXPECTATION_SCHEMA_VERSION` stays 1.2.0: the expectation's required fields
and `SUPPORTED_DIMENSIONS` are unchanged, and `_require_matching_provenance` already binds every
expectation to `checker_digest == package_digest()`, the exact running package, before any
dimension is read, so no expectation is evaluated against a delta shape it was not written for.
Limit: the boilerplate set names one import by exact `(target_module, symbol)` pair, not a
pattern, so a second language-boilerplate import would need its own entry the way this one was
added. Check: `tests/test_delta.py::test_one_module_with_one_intra_component_import_is_one_semantic_change`
reproduces the `labels.py` shape and asserts exactly one `dependency_edges` addition;
`tests/test_delta_parity.py`'s golden digests moved with `DELTA_SCHEMA_VERSION`'s own bytes,
covering import records unaffected by either cut; `docs/roadmap.md` records 7 -> 1.

