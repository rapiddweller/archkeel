# AD-746: A test is not a reason for a name to be public

Status: accepted (lead decision, #1510). Part of #880.

#1436 and #1438 stated `external_users` in the contracts for names that only tests use. That made a
rule pass because a test reads the name, which the honesty rule forbids: the findings were hidden, not
fixed.

Decision: a test is no user for `NATIVE-PUBLIC-HAS-A-USER` or `SHELL-PUBLIC-HAS-A-USER`. The cause is
fixed in the code, name by name:

- Python: the name gets a leading underscore (L-256: tests may import an underscore name).
  `core_arguments._VARIABLE`, `core_frame._NAMES_A_GAP_EXIT`, `core_frame._UnknownKind`,
  `init_draft._PAGE` and `native_scan._TIMEOUT_SECONDS`.
- Rust: `MAX_SCAN_BYTES` and `MAX_NESTING` of `archkeel-snapshot` are `pub(crate)`. The `charged_bytes`
  and `read_bytes` probes of `test_tree` are deleted; the two counters stay in `work.rs` under
  `cfg(test)` for the tests of the snapshot crate. The tests of `archkeel-collect` state the two limits
  as constants and measure the charge from the files that the reply names as inputs. A drift of a limit
  fails the tests that scan to the exact byte below and above the cap.

The Rust collector counts an item behind `cfg(any(test, feature = "test-tree"))` as public in the
normal build (`test_tree::read_bytes` was a finding). So a test-support module under a feature is not a
way out: it would be a public name with no user. That is why the probes are gone and not moved.

The 9 `external_users` entries are removed. The entry `archkeel.cli:main` stays: the console script is
a real consumer outside the scan. The contract feature stays for real consumers, such as the users of a
library.

Known gap, filed as #1549: a rule that passes because of a stated external user shows a plain PASS, not
"PASS assuming stated external users" as a declared door reach does.

Consequence: `reads` is no longer in the `SCAN_INPUT` line of the measurement test, and `charged` is
the sum of the input files. No test read `reads`. `_VARIABLE` was only a name for the ignored switch
`ARCHKEEL_CORE_ONLY`; no code read it. The owner approved its deletion; the switch stays accepted and ignored.
