# AD-394 Stop the TypeScript deletion on nested verdict differences

**Status.** Deletion stopped. Part of #880. This draft changes no production code, dependency or asset.

**Decision.** Keep the Python analyzer and the existing launcher. Do not delete them while the native host verdicts differ.
The six collector parity files alone are not a deletion gate. Compare the full TypeScript dual-run corpus, including mounted contracts.
Add strict xfails for the measured gap. Do not change a verdict oracle to hide the gap.

**Required deletion contract, taken by the lead.**
1. Use only the native TypeScript collector. Missing or unverified binaries must give a named environment error, exit code 2, and no verdict.
2. Keep an explicit `collector_argv` unchanged. Never fall back to less evidence or another collector.
3. Before deletion, record exact Python replies with their main SHA and Python version. Keep deterministic order and a retired recording procedure.
4. Prove the recording before deletion, including one-byte corruption and ten separate faults. Preserve user-visible native tests and list removed internal tests.
5. State function and parametrized-case counts before and after. Run every corpus and demo. Stop deletion on any unexplained difference.
6. Remove only Python-specific dependencies, assets, pins and tools. Keep `ir/` and `check/` from growing. Document each supported install.
These changes are not retained in this draft because the parity gate stops them.

**Final parity statement.** Python 3.11.12; analyzer source `2a3b6eca07d87b23bea4ac2176c22a7a12ceac05`.
The corpus folder is the local `bench-interim/corpus`. No corpus is changed.

| Set | Files | Equal | Named differences | Different |
|---|---:|---:|---|---:|
| Repository fixtures and Studio UI, syntax | 113 | 113 | none | 0 |
| Four fixtures and Studio UI, collector facts | 78 | 78 | producer metadata only | 0 |
| 53 original TypeScript demo variants, root verdicts | 372 | 372 | producer metadata only | 0 |
| Excalidraw, syntax; also full reply and records | 723 | 723 | none | 0 |
| x35, syntax; also full reply and records | 910 | 910 | none | 0 |
| fastapi, flutter, priv-py, pydantic and uv, syntax | 33 | 33 | none | 0 |
| dart-http and priv-dart | 0 | 0 | no TypeScript/JavaScript source | 0 |
| Full host corpus, 208 TypeScript projects | 1,480 | 1,275 | five projects, 15 rule verdicts and five scope rows | 205 |

The last row counts files in equal or different projects, not individual changed source files.
The dual-run tool reports 20 differences. The Python engine matches its committed oracle on all 208 projects.
The existing hostile-source test also names nine Python depth failures; native returns facts (AD-323). These are known oracle limits.

**Different projects.** `fixture/L-nest-realworld`, `demo/nest-realworld-project`,
`demo/nest-realworld-forbidden-edge`, `demo/nest-realworld-signature-fail`, and `demo/nest-realworld-dynamic-unknown`.
Each project changes these mounted `REQUIRES-COMPLETE` rules from PASS to UNKNOWN:
- `API composition`
- `Account and authentication`
- `Article and comment publishing`
Each project also differs in the first scope row reported by the tool: `RULE-EVALUATION-03f1490d74c5e94d`.
Its dependency-scope proof records the Rust runtime instead of Python.

**Cause.** `ir/decisions.py::_native_scope_runtime_valid` accepts only `runtime.name == "python"`.
`_scoped_dependency_receipt` uses that check, so it rejects the Rust collector's proof. AD-352 covered member inventories, not this receipt.
The earlier parity helper compares root assessments and record kinds; it does not compare the complete mounted verdict map.

**Install truth.** Full builds six native wheels: Linux glibc x86_64/aarch64, Linux musl x86_64, macOS x86_64/arm64 and Windows x86_64.
The release workflow sets `PUBLISH_NATIVE_WHEELS=false`. Those wheels are built, but are not added to published distributions.
A pure wheel, sdist install and editable install contain no binary. The sdist does not contain the Rust workspace.
`make native-tools native-wheel` is the existing source-checkout build path. This draft leaves all install behavior unchanged.

**Proof kept.** Before stopping, recorded tests passed with Python still present: 259 passed and one known strict xfail.
Ten separate golden faults failed the migrated resolution-grid test. An additional 421 parser cases passed native comparisons.
The recordings and working evidence stay outside the repository. No test file is deleted, and all six live oracle files remain.
The new regression adds one test function with 15 strict-xfail cases; it covers every changed rule in all five projects.

**Open points.** `TS-RECEIPT-RUNTIME`: define trusted native receipt replay without weakening proof checks.
`TS-WHEEL-PUBLICATION`: the lead must decide wheel publication before a native-only deletion can merge.

**Check.** `tests/test_collector_native_nested_verdicts.py::test_native_collection_preserves_each_mounted_requires_verdict`.
Do not merge this finding as the deletion. Resume deletion only after the full host corpus has no unexplained difference.
