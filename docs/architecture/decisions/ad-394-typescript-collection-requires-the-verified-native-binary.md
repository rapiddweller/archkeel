# AD-394 TypeScript collection requires the verified native binary

**Decision.** Remove the Python TypeScript analyzer, its launcher, grammar dependency,
standard-library assets, parser-only tests and exclusive policies. Part of #880.
Keep exact recorded Python output as the independent migration oracle.
Do not regenerate these recordings from the native collector.

**Runtime guard.** Commit `b0ba7886cb988dd1a2b62ce254f396bad01555b3` introduced
[AD-227](ad-227-scoped-dependency-proof.md) for #493. Its runtime guard protects safe replay
of complete dependency scopes across unrelated source gaps. It validates saved Python
numeric lower bounds. It does not use interpreter-specific resolution for these scopes.
Physical inventory, contract authentication, ownership, source, evidence, permission and
gap bindings remain mandatory. No other receipt check changes.

The bundled collector is a compiled program. Its executable bytes identify its runtime.
The shell's `observe.verified_binary` checks these bytes against the installed SHA-256 file
in each collection. Only a successful check creates the typed, host-only `VerifiedBinary` fact.
The process checks the digest again before launch. Failed collection produces no trusted facts.
A configured `collector_argv` never receives this fact, even when pinned or named Rust/Python.
The receipt records `runtime.code_digest`. Replay compares it with the verified executable digest.
Unverified producers, missing digests and other digests give named UNKNOWN reasons.
Saving and loading a report cannot recreate live trust. Saved native partial scopes stay UNKNOWN.
The previous Python receipt checks remain unchanged.

**Install.** Enable `PUBLISH_NATIVE_WHEELS=true` for the next owner-started release only.
Full builds `manylinux_2_17_x86_64`, `manylinux_2_17_aarch64`, `musllinux_1_2_x86_64`,
`macosx_10_12_x86_64`, `macosx_11_0_arm64`, and `win_amd64`, with binaries and digest files.
A pure wheel, sdist or editable install contains no binary. The sdist omits the Rust workspace.
TypeScript then stops with `typescript_collector_missing_binary` and environment exit code 2.
The error gives the native-wheel install command and the source-checkout build command.
There is no Python fallback. An explicit `collector_argv` keeps its existing behavior.
This change does not start a release, publish a package or merge a PR.

**Oracle.** Source `2a3b6eca07d87b23bea4ac2176c22a7a12ceac05`, Python 3.11.12.
The manifest binds 5,378 recorded calls to their test IDs and exact archived byte digests.
The additional 102 calls use unchanged Python source in the owned reference worktree.
The retired recorder documents the original procedure and refuses new capture.
Retained Core tests compare native facts first, then use recorded Python provenance.
The permanent host parity helper compares every mounted rule, not only root assessments.
The 15 Nest mounted-rule regressions are ordinary tests, not expected failures.

**Rejected.** Runtime-name exceptions, configured-collector trust, wire attestation fields,
changed verdict oracles, a silent empty scan and a retained Python fallback.
**Ratchet exception.** D1 uses the lead's named allowance: `ir` plus `check` grow by 27 lines.
The bound amendment records exact new verification ports and the moved metadata types.
The Python self-scan has zero violations. After the conflict-required rebase onto #1094,
its measured unresolved-call pin changes from 1,025 to 1,048. No other budget changes.
**Checks.** `test_collector_native_receipts.py`, `test_collector_bundled_launcher.py`,
`test_collector_native_nested_verdicts.py`, the six collector parity files and recorded parser probes.
The PR records final corpus, deletion, fault-injection and gate results. Keep it draft until all pass.
