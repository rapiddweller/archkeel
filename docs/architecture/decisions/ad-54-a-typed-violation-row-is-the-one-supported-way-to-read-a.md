# AD-54 A typed violation row is the one supported way to read a report's violations, and `ir.baseline` derives it once for everything that groups them

`ir.baseline.ViolationRow`
names one violation the way a consumer off disk reads it: `fingerprint` (AD-52's `(rules,
subjects)`), `source_module`, `target_module`, `symbol`, `source_component`,
`target_component` and `evidence_ids`; a field a violation kind carries no value for, such as
a forbidden construct's `source_module`, is `None`, never guessed. `rules` and `subjects` live
only on `fingerprint`, not repeated at the top level too: two copies of one value is one more
place for them to drift, so a caller reads `row.fingerprint.rules`.
`ir.baseline.violation_rows(observation)` derives one row per violation record, and both
`observed_violations` (AD-52) and `ir.decisions.violation_counts` (AD-51) now build on it
instead of their own loop over `observation.records("violations")`, so a baseline comparison
and a rule-and-pair breakdown can never disagree with a consumer's own rows about what a
violation is or which component pair it crosses. `ir.codec.load_observation(path)` reads one
`architecture.json` from disk and returns its `Observation`, composing `decode_json`,
`decode_canonical_model` and `parse_observation` so a consumer calls one supported function
instead of three internal ones against a columnar, string-interned file; `ir/digest.py`
already reads files to hash the installed package, so this is not the first I/O in `ir`, only
the first that reads a report a consumer supplies. Because that file may be hand-edited or
truncated, `ir.codec.parse_record` now rejects a VIOLATION record whose `rule_ids` is empty
with a named `ValueError`, closing a gap `schema/architecture-ir-common.schema.json` already
documented (`minItems: 1`) but nothing enforced at runtime: `violation_counts` indexes
`fingerprint.rules[0]` unguarded, on the correct assumption that every violation
`embedded.violations` produces carries one, and an untrusted file read back through
`load_observation` needed the same guarantee, checked at the boundary where the untrusted
bytes enter rather than papered over with a fallback where the value is used. Reason: issue
#12 - a CI gate reading `architecture.json` from a test had only `ir.codec.decode_canonical_model`,
an internal module, to get named fields from, the same gap datamimic CE hit before AD-52. The
issue's two suggestions were rejected: a new `archkeel.api` package would be a second,
undeclared public surface beside the `public` list this repository already has (AD-9), and a
third JSON shape for violations would compete with `violations_by_rule` and
`violations_by_component_pair` (AD-51), which the result already carries, and would let
`architecture.json`'s digest-bound bytes diverge from what a report promises. Rejected: a new
`ir/violations.py` module, because `ir.baseline` already derives what a violation is (AD-52)
and a fourth loop over the same records would be one more place for the three to disagree, not
fewer; repeating `rules`/`subjects` beside `fingerprint` on `ViolationRow`, an ergonomic
shortcut that would have let the two silently disagree, since nothing ties a dataclass field to
another one. `ViolationRow`, `violation_rows` and `load_observation` add nothing to any
component's `public` list: that list is AD-9's internal cross-component control, populated by
what another Archkeel component actually imports across a boundary, and nothing inside this
repository imports these three - only a consumer outside it. Adding them by hand would have
made `architecture-contract.json` diverge from `init`'s own drafted proposal, the SPOT guard
`tests/test_self.py::test_self_contract_public_matches_drafted_proposal` holds it to. What did
move: the two new names in `ir.baseline` dropped the share of its public names that another
component uses under half, so `init` now drafts `ir.baseline`'s entry as three symbols,
`KnownViolation`, `compare_violations` and `observed_violations`, instead of the whole module;
`architecture-contract.json` follows that draft exactly, as it already did before this change.
Limit: `load_observation` performs I/O, which `ir/digest.py` already did before it, so `ir`'s
"no I/O" reading in AD-17 always meant no I/O in a *derivation* over already-read evidence, not
a blanket rule this function breaks; both are entry points that read one file a caller names
and hand its bytes to the pure code beside them, nothing more. `ViolationRow` promises nothing
about the columnar file format itself, nor about any `ir` module's internals beside
`ir.baseline`, `ir.codec` and `ir.decisions`, which `architecture-contract.json` already lists
as public. Check: `tests/test_violations.py`'s
`test_load_observation_reads_the_canonical_report_bytes_back`,
`test_violation_rows_type_an_import_violation`, `test_violation_rows_leave_construct_fields_none`,
`test_violation_rows_fingerprints_agree_with_ir_baseline`,
`test_reference_md_snippet_reads_a_report_and_lists_its_rows` and
`test_load_observation_rejects_a_violation_with_no_rule_ids`, all against the `tour` demo
variant (AD-11) except the last; `tests/test_decisions.py::test_violation_counts_group_the_report_by_rule_and_by_crossing_pair`
and `tests/test_baseline.py` passing unchanged; `tests/test_self.py::test_self_contract_public_matches_drafted_proposal`
against the corrected `ir.baseline` entries; and `archkeel validate --root . --json` on
Archkeel's own contract.
=======
**AD-53 `from pkg import name` follows `pkg/__init__.py`'s own binding before a same-named
submodule.** `imports.collect_package_bindings` reads every scanned `__init__.py`'s unconditional
top-level statements once, before any module's imports are resolved, and records the names each
package binds to something other than the identically named submodule: a `def`, a `class`, an
assignment, an aliased import, or a `from` import naming anything else. `ImportCollector` now
prefers that binding over the submodule interpretation it used alone before: `from pkg import
name` reads as the name `pkg:name` when `pkg/__init__.py` shadows it this way, and as the module
`pkg.name` otherwise, the way `import pkg.name` already resolves. A
plain `from . import name` is read out of the shadow set on purpose, because that statement binds
the identically named submodule itself; over-correcting it into an attribute would misread the
ordinary submodule re-export idiom as its own shadow. `ANALYZER_VERSION` rises to 0.24.0 (AD-3).
Reason: CPython's `_handle_fromlist` checks `hasattr(pkg, name)` before it ever imports a
submodule of that name (issue #23), so a package that assigns, defines or re-exports a name
shadows its own submodule at runtime; the scanner read only the submodule's existence and got
`interface_boundary`'s subject and `dependency_edges`' target wrong whenever the two collided,
an accident CPython treats as ordinary shadowing. Rejected: resolving this per module instead of
once up front, because a module can import from a package the scanner has not visited yet, and
`collect_package_bindings` already costs the cheapest possible pass, one walk of each
`__init__.py`'s own top-level statements; reusing `symbols`, because it never records a plain
assignment; reusing `bindings`, because it answers a different question, an unused function-scope
local rather than a module-scope shadow; expanding a star import inside `__init__.py` to decide
the names it introduces, because that reaches into a second module's exports for one case the
issue does not ask for. Limit: a `__getattr__` or a star import in `pkg/__init__.py` still makes
every one of its attributes undecidable, and the scan keeps the submodule-if-it-exists reading
for the whole package there, which is `docs/rules.md`'s narrowed #23 blind spot; a name bound
inside `if`/`try` is not seen either, matching `literal_all_exports`. Check:
`tests/test_analyzer.py::test_from_import_binds_the_package_attribute_over_a_same_named_submodule`,
`tests/test_analyzer.py::test_from_import_of_a_re_exported_submodule_still_resolves_to_the_submodule`,
and `fixtures/demo_catalog_interfaces.py`'s
`class-a-interface-boundary-package-attribute-over-submodule` row, where `shop.store`'s own
`sqlite` attribute makes `shop.app`'s crossing an `INTERFACE-BOUNDARY` violation instead of the
`DEP-APP-NO-STORE-SQLITE` forbidden-dependency violation the old resolution produced on the
untouched submodule.
>>>>>>> origin/main
