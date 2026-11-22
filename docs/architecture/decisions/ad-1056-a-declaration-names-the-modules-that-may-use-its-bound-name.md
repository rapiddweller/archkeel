# AD-1056 A declaration names the modules that may use its bound name

**Status.** Accepted (owner decision, 2026-11-22). It refines the exposure check of [AD-1052](ad-1052-a-contract-declares-a-trojan-horse-site-by-its-name.md).

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** AD-1052 refuses a declaration on an import when another module can reach the bound name (an import, or an attribute or a text of that name). One honest use then blocked the whole declaration. In datamimic-ce, `importlib.resources.files` in `datamimic_ce.interfaces.cli.runtime` kept 99 rules UNKNOWN.

**Decision.** Contract 3.20.0 adds the optional field `covers`: a list of module prefixes, like `loads`. A module that can reach the bound name and lies below a `covers` prefix does not refuse the declaration. A module that can reach the name and lies below no prefix still refuses it (`trojan_horse_reach.invalid`). Each frame row of an applied declaration lists the covered modules in `covered`, and the text report prints `Covered uses of the bound name`.

**Limits.** `covers` is a premise of the contract, like `loads`: it is trusted. The scan does not prove that a covered module uses the name harmlessly. The row and the "PASS under" words say so. A prefix that names a module that never reaches the name is not an error.

**Measured.** Scratch copies without `.git`, 86 and 57 declarations by name, `loads: []`: datamimic-ce 99 to 36 UNKNOWN (1 FAIL stays, 239 PASS: 176 unconditional, 63 under declared reaches). datamimic-ee needs no `covers` (24 UNKNOWN, 0 FAIL, 455 PASS: 256 unconditional, 199 under declared reaches).

**Tests.** `tests/test_cli_python_trojan_horse_name.py`: a covered use clears and is listed; an uncovered use stays refused and Python really imports the module.
