# AD-52 A violation is named by what it is, and a baseline may hold the ones already there

`ir.baseline` fingerprints violations by sorted rule ids and subjects, not source
positions. The evidence-linked `VIO-` id remains separate. Shared fingerprints,
such as two `getattr` calls in one function, carry counts.

`validate --baseline <file>` requires exact observed counts: understated debt is
new; overstated debt is resolved. Both exit 1 with failures. An exact baseline
exits 0 while `declared_rules` remains FAIL and violations remain visible.
Only `rule.violated` is baselined; other diagnostics and unreadable baselines
(`baseline.invalid`) exit 2. `--write-baseline` writes observed counts only from
runs not exiting 2. Other commands and validation without a baseline are unchanged.

Target-first validation otherwise fails on known debt. Permitting those edges in
the contract would also permit new imports. A shrinking baseline retains intent;
DATAMIMIC CE had previously built this through internal codecs.
Readable structured fingerprints support review (#11): titles are unstable,
opaque hashes hide meaning, and delimiters can occur in component labels.
Exact counts prevent resolved debt returning under stale allowances.
The analyzer version remains 0.22.0; no observation record changes.

Limits: renaming owners or moving modules resolves one fingerprint and introduces
another. Shared subjects cannot identify individual occurrences. The baseline is
compared, not authenticated by `check`; widening prevention was left to #11.

Checks: `tests/test_baseline.py` covers line relocation, shared counts, new and
resolved debt, preserved diagnostics and invalid files; CLI write/gate tests and
schema drift tests cover serialized round trips.
