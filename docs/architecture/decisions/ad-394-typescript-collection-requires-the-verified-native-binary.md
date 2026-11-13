# AD-394 TypeScript collection requires the verified native binary

**Decision.** Remove the Python TypeScript analyzer, launcher, grammar dependency, runtime
catalog and exclusive policies. Keep public recorded Python output as the independent oracle.
Native output never supplies a recording. Part of #880.

**Runtime guard.** AD-227 protects safe partial-scope receipt replay, not Python-specific
TypeScript resolution. Only observations of the Python analyzer keep the Python lower-bound path.
TypeScript, Dart and Rust runtime-name claims give `dependency_scope_runtime_unverified`.
For TypeScript, only this run's verified bundled executable digest can prove a partial scope.
Configured collectors and saved JSON do not acquire native receipt trust.
Physical inventory, contract, source, evidence, permission and gap bindings remain mandatory.

The shell's `observe.verified_binary` checks executable bytes against the installed `.sha256` file.
Only that check creates the typed, host-only `VerifiedBinary` fact. The process checks the pin again.
The receipt binds `runtime.code_digest`; replay compares it with the verified executable digest.
Missing, wrong and unverified digests retain named UNKNOWN reasons. No new wire field is added.
The `.sha256` sits beside the binary. An attacker who can write both, or installed Python code,
is outside this trust claim. Keep the existing read-to-exec limit documented in `pin.py`.

An earlier implementation in this change copied facts after decoder registration. Main did not
have that defect. The copy lost validation identity and store ownership. Attach host metadata in
the decoder before registration. The fail-first store test and real CLI reproduction check this.

**Install and release.** The next owner-started release publishes exactly six platform wheels
and one sdist: `manylinux_2_17_x86_64`, `manylinux_2_17_aarch64`, `musllinux_1_2_x86_64`,
`macosx_10_12_x86_64`, `macosx_11_0_arm64`, and `win_amd64`. Do not publish the pure build wheel.
The release step refuses a different wheel or sdist count. Keep `PUBLISH_NATIVE_WHEELS=true`.
Windows ARM64, musllinux aarch64, Linux ppc64le/s390x/armv7 and BSD lose TypeScript scanning.
Without a supported native collector, scans fail closed with exit 2, not an empty scan or PASS.
Pure builds, sdist installs and editable installs contain no binary. The sdist omits Rust source.
Build from a Git checkout with `make typescript-collector`, or install a supported native wheel.
This change starts no release, publication or merge.

**Oracle.** Record only the checkout's public fixtures/tests and the named public Excalidraw root.
Reject other source roots and symlink escapes before recording. Verify the public root's origin.
Generate fixture roots inside the checkout's ignored test-artifacts directory.
Group each test's calls in one compressed member. Bind the main SHA, archive and member digests.
Missing keys fail by name. A test checks source provenance before replay.
Regenerate parser probes from public main tests, never from previous recorded facts.
Compare full main host verdicts with the verified native host, including all 15 mounted PASS cases.
Core fixtures use the same shell verification; Python runtime metadata gives them no native trust.
The fixed authored `TARGET-PROFILES` intent retains eight port-widening controls.
Studio UI comparisons visibly skip when their dependency is absent and name the existing Make target.

The harness pins producer version and inventory runtime identities only. Receipt content, every
verdict, member, edge and gap still compare. Keep the permanent complete mounted-verdict check.

**Full-gate cleanup.** macOS returns `EPERM` for an exited, unreaped Studio group leader.
Reap and retry the same signal once. A repeated denial still fails closed. Keep descendant cleanup.
Portable denial tests and a real macOS kernel regression check both paths.

**Ratchet.** The lead allows at most 63,968 + 45 lines in `ir` plus `check` for this fix.
The amendment binds exact decoder ports, moved metadata types and the measured call inventory.
Removing the package removes the only in-repository candidates for calls such as `.resolve`,
`.decode`, `.read` and `.is_file`. Retained calls change from partially resolved to unresolved.
This is the main cause of the +23 net count; verification and cleanup also add calls.
Keep every other budget, Any restriction, receipt check and rule unchanged.

**Rejected.** Runtime-name exceptions for native languages, configured-collector native trust,
wire attestation fields, native-generated oracles, external input capture without a public allowlist,
changed verdict expectations, a silent empty scan and a retained Python fallback.
