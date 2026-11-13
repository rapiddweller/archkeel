# AD-422: Delete the Python language collectors

## Decision

The owner accepts this support reduction on 2026-11-13 (lead log L-119, issue #880).
Delete the Python implementations of the Python, Dart and TypeScript collectors now.
Keep every Rust crate under `native/`, including the future Python and Dart collectors.
Keep the Python shell, IR, checks and renderers until the native core replaces their paths.

Rust and TypeScript projects remain supported through the native collectors.
Python and Dart projects are not supported in this version.
Use archkeel 4.0.1 for those projects, including saved facts and baseline commands.
An unsupported profile gives a typed refusal before collection, exit 2, and no partial verdict.
A configuration cannot authorize a supported subset of an unsupported project.

The root Python self-check stops because it needs the deleted Python collector.
The native self-check stays mandatory, with its pinned gaps and violations.
CI publishes the Rust self-report instead of measuring the unsupported Python root report.
The gallery names and counts unsupported demos before collection. Its TypeScript demos stay live.
Lint, type checks and tests of retained code stay mandatory.
Delete tests that serve only the deleted implementations. Do not create recordings for them.
Keep native unit tests. Name parity tests as skipped until their released oracle is connected.
The dual run names and counts each unsupported Python and Dart case.

## Rejected alternatives

Keeping the old collectors preserves two implementations and delays their removal.
Recording each old test preserves maintenance work without a live supported collector.
Checking only supported files can give PASS for an incomplete project.

## Limit and return path

Python and Dart return only when their Rust collectors exist and the store accepts their replies.
Use the released 4.0.1 as the later comparison oracle, not deleted source or new recordings.
Restore the Python self-check only after that end-to-end path works.
TypeScript collection requires a native platform wheel or a local native build.
No Python fallback exists on platforms without a shipped native binary.
The next owner release must publish six platform wheels and one sdist, never a pure wheel.
The release step refuses false publication flags and incomplete artifact counts.
The colocated digest detects a changed binary, not an attacker with install-write access.

## Checks

`tests/test_cli_unsupported_projects.py` checks fail-first command and direct-entry refusals.
The typed exception retains a `missing_tool` diagnostic, exit 2 and the released-version remedy.
Studio refuses an unsupported profile before it can start or reuse a server.
Historical Python and Dart configurations refuse before a supported candidate is collected.
`tests/test_dependency_runtime_identity.py` checks the analyzer identity before Python runtime trust.
`tests/test_native_ci.py` runs the release shell step with complete and incomplete artifact sets.
The native self-check and Rust/TypeScript dual run check the retained paths.
