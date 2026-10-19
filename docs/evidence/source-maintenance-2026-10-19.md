# Native source-maintenance checkpoint

`SOURCE-MAX500` in the root Contract 3.8 owns the 500-line ceiling and file
selection. It covers maintained sources, tests, tools, Makefiles and workflows.
Four pinned upstream manifests and six exact generated/vendor hashes exclude
259 files. There is no oversized-source allowance; the zero-violation baseline
and all coupling ceilings remain unchanged.

Input acquisition owns bytes and snapshot identity. Core evaluates sizes;
saved receipts verify the declared selection, every candidate classification,
manifest contents and exact findings. Missing evidence cannot certify PASS.
Two reproduced replay holes and the legacy observe-adapter gap were fixed.
File-inventory gaps preserve independently proven source-rule coverage.

Source-spelling privacy now has one decision owner in `ir.source_records`.
The nominal vocabulary and wire reader remain in `ir.facts`; dunder API rules
remain distinct. The Contract names the actual SPOT owner and copy controls.
Interface values moved behind the existing import facade: `interfaces.py`
438 lines, `interface_values.py` 85. Its tests split by responsibility into
338 and 279 lines, preserving test bodies. One obsolete long-function
exception was removed.

LOCAL VERIFIED:

- Lint and Mypy: PASS, 163 checked source files.
- Collector safety: 437 PASS.
- Contract, replay, snapshot, profile, interface and hygiene controls: 767 PASS.
- Build, strict package validation and wheel/sdist smoke: PASS.
- Four isolated SPOT assertions against the actual native self-observation:
  PASS, including copied identity/privacy-owner detection.
- All six declared coupling budgets remain within their unchanged ceilings.
- Astra reviewed maintainability, reliability, extensibility and performance;
  the implementation checkpoint has no remaining material code findings.

Native acceptance remains **FAIL**: 126 rules PASS; `SOURCE-MAX500` reports
148 violations and two symlink inventory gaps. The report contains 669 maintained
file facts. The shared self-test fixture correctly rejects these violations;
it was not relaxed. Unresolved calls are 854 against the unchanged budget 838;
that still needs correction before complete baseline acceptance.

CI-ONLY VERIFICATION: not run. This checkpoint is not merge or release approval.
Repository-inventory overhead and further performance improvements are unmeasured.
