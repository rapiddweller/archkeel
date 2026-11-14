# AD-442: Windows disk roots use one plain canonical path

## Status

Accepted. Part of #880.

## Reason

The shell resolves a Windows disk root with a drive letter and no verbatim prefix.
Rust adds the verbatim prefix `\\?\` in `fs::canonicalize`.
The text comparison refused every ordinary Windows project before collection.
Contained reads also need the same prefix as their root.

## Decision

On Windows, accept only absolute disk prefixes from `std::path::Prefix`.
Remove only the verbatim disk prefix, and only for ordinary Win32 file names.
Refuse network, device, volume and other verbatim prefixes before a filesystem read.
Refuse names whose meaning changes without the verbatim prefix, including reserved device names.
Use the plain form for the root comparison, reported root and contained reads.
Keep the exact canonical text comparison after this one change.
Do not fold path case, remove a trailing separator or accept forward slashes in the core request.
Do not resolve a short name or a junction by changing the requested root in the core.

The shell uses `Path.resolve` before it sends a request and before it binds the frame.
That call resolves drive case, separators, short names and links on the filesystem.
The shell removes the verbatim disk prefix from its resolved root too.
It refuses other Windows prefixes before resolution, so a device path cannot become a disk root.
A caller that sends a noncanonical root directly to the core still gets a refusal.
A configuration or scan root that resolves outside the project still gets no bytes.
Unix path handling does not change.
The tree binding uses this same resolved form for the root, configuration and all contract files.
Contract file lists keep POSIX references with `/`, including on Windows.

There is no 260-character root limit. The filesystem APIs accept long disk paths.
The Windows scan test uses a root longer than 260 characters and repository-local `core.longpaths=true` for Git.
If the fixed Git executable cannot read a repository, its error remains a typed refusal, never PASS.

The snapshot crate already compares canonical roots with canonical targets in the same namespace.
Its `snapshot.rs` and `listing.rs` canonicalization calls need no prefix conversion.
They report relative file identities, not that internal absolute root.

## Rejected alternatives and limits

Do not remove every `\\?\` prefix: this would accept unsupported namespaces.
Do not compare paths without their prefixes: this can join unrelated roots.
Do not add a dependency for this disk-prefix conversion.
Do not lift the Windows wheel release guard in this change.
No local Windows execution is available. A cross-target check is not runtime proof.
Short-name tests use the name that Windows supplies; a volume can have 8.3 names disabled.

## Checks

`native/collect/src/repository_tests.rs` tests the text table on each host.
Its Windows tests use real canonicalization, contained reads and a directory junction.
Its existing Unix tests keep the canonical-root, symlink and work-budget checks.
`tests/test_cli_windows_root.py` checks release-core PASS and FAIL exits.
On Windows it checks shell spellings, a junction, unsupported prefixes and an escaping configuration.
Full verification runs these tests in `native-wheel-windows` on `windows-2025`, after merge on main.
The ordinary CI jobs use Linux. They cannot prove Windows runtime behavior.
