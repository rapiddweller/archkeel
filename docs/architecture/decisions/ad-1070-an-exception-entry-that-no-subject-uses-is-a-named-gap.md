# AD-1070 An exception entry that no subject uses is a named gap

**Status.** Accepted for issue #1986. The issue proposes the UNKNOWN class. The owner has not
chosen between UNKNOWN and FAIL: this record implements the proposal.

**Reason.** A rule lists exceptions: `allowed_sources`, `exact_sources`, `allowed_type_ignores`.
An entry that names no subject of its rule protects nothing. It looks like a reviewed decision and
can hide a new violation later. `import-linter` reports such an entry; ArchKeel said nothing.

**Decision.**
1. **One mechanism.** An unused entry is a contract hygiene row (`Reason::Hygiene`), as a
   `trojan_horse_reach` declaration that matches no trojan horse (AD-664) and a `boundary_types`
   exception that matches no position (AD-550) already are. It has the code `unused_allowance`.
   `--json` gives a gap with `kind: unused_allowance`. `--text` names the rule id, the field and
   the entry.
2. **UNKNOWN class.** The row holds back a PASS. A run without a FAIL reads UNKNOWN with exit 2. The row never makes a FAIL: the
   contract is stale, and the code is not wrong. The rule keeps its own verdict.
3. **A subject is read by the matcher of the rule.** Each matcher module (`direction`, `placement`,
   `construct_match`, `boundary_surface`, `receipts`) lists the subjects of its rule before its
   exceptions apply, and `scope_receipt::unused_allowances` asks the one that fits the rule kind. An
   entry is used when it names a module, caller or ignore of one such subject. An import, a class, a
   call, a construct or a public facade is a subject. The check keeps no second copy of the matching
   rule, and it adds no module to the self-check (the base comparison shows no growth).
4. **Fields.** The check covers `forbidden_dependency.allowed_sources`;
   `external_dependency_scope`, `symbol_placement`, `call_owner`, `forbidden_construct` and
   `boundary_types`: `allowed_sources` and `exact_sources`; and
   `forbidden_construct.allowed_type_ignores`. `boundary_types.allowed_positions` keeps its row
   `boundary_type_allowance_stale` (AD-550); its keyed ids and accepted lists stay.
5. **Not covered.** `allowed_dependency` records permission without an observed import.
   `root_layout.allowed_children` is layout. `interface_boundary.module_object_grants` is not read.
6. **When the check stays quiet.** The collector proves only some subjects, so a class of an
   unproven kind has no record (AD-550). A `symbol_placement`, `call_owner`, `forbidden_construct`
   or `boundary_types` rule that judges no subject at all reports no entry. An import rule reports
   even then, unless an import that the scan cannot resolve can come from the module of the entry.
7. **Fixtures and self-checks.** The self-contract `native/architecture-contract.json` had 74 unused
   entries. All are deleted. The shell contract, the Studio UI contract and the `shop` fixture have
   none. `python-newer-syntax-demo` gets the call `sweep` in `sample/maintenance.py`, so the entry
   `sample.maintenance` is used. The one entry of `EXTERNAL-SHOP` in `H-typescript` stays: that rule
   shows a package that no import names (AD-1048), so no entry can be used. `fixtures/matrix.json`
   pins the gap.

**Limit.** An entry that matches a subject only through a gap is not reported. The check reads
whole entries, not the parts of a prefix. A rule with several kinds hides an unused entry while
another kind judges a subject.

**Tests.** `tests/test_cli_unused_allowance.py`: the example of the issue and the text (items 1
and 5), an entry that matches a real import (item 2), each field of point 4 (item 4) and a reviewed
type ignore that no written ignore matches. `tests/test_native_self_core_rows.py` and
`tests/test_cli_shell_self_check.py` require no gap in the self-checks (item 3).
`tests/test_cli_fixture_matrix.py` pins the fixtures.
