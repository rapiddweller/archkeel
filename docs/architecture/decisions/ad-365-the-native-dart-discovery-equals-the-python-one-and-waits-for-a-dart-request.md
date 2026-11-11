# AD-365 The native Dart discovery equals the Python one and waits for a Dart request

**Status.** Accepted. Epic #880, PR 8 slice 1. It follows AD-342. AD-368 adds the Dart request.

**Decision.**
1. The crate `native/dart` (`archkeel-dart-collector`) holds the discovery of the native Dart
   collector. It selects and reads the `.dart` files of each scan root, as
   `analyzer/dart/snapshot.read_snapshot` does. Each read goes through `archkeel-snapshot`.
2. The collector follows no symbolic link. `archkeel-snapshot` gets a walk without links:
   `Snapshot::open_root` refuses a snapshot root that is a link or not a directory, `check_root`
   resolves the real path of each scan root once, `listing` gives each link as `Entry::Link`
   and walks each real subdirectory, and `read_walked` reads only a file of a walked directory.
   It compares the file before and after the open (device and inode), as the Python `samestat`
   check does. The symlink rule and the containment stay in the snapshot crate.
3. Each problem that `archkeel-snapshot` records (a name that is not UTF-8, a directory or a
   file that cannot be read) becomes a `SnapshotError` gap. Nothing that the walk cannot see is
   silent. A repeated scan root is read once, as `snapshot._roots` does.
4. The crate builds the sections that the discovery decides, with the Python rules: the inputs,
   the source listing, the scope, the selected files, a file fact for each source, a gap for
   each snapshot problem (kind, title, subject and data at line 1) and their evidence. The
   decode of `pubspec.yaml` and the Python text rules (`splitlines`, `strip`) are ported.
5. A source over `MAX_FILE_BYTES` (4 MiB) is a `SnapshotError` gap and not a source. The Python
   collector has no limit; this is one of the closed exceptions of #880.
6. The protocol has no Dart request: `Resolver` in `archkeel-facts` has no `dart` variant, and
   protocol 10.0.0 adds only `python`. The binary refuses a request with exit code 2. The wheel
   does not carry it and the host has no launcher for it, so a native Dart reply cannot give
   PASS. Until a request exists, the test-only feature `dump` adds `--dump <root> <namespace>
   <root>...`, which prints the sections (AD-323).
7. Parity gate: `tools/dart_discovery_parity.py` compares the sections with the Python reply.

**Problem.** Slice 5 switches the Dart default only when each section equals the Python reply.
The discovery is the first part that the other slices use.

**Rejected.** (a) Define Dart settings in the collector crate: AD-345 gives each wire type one
definition in `archkeel-facts`. (b) Follow a link inside the snapshot, as `Snapshot::entries`
does: the Python collector names each link as a gap. (c) Give no file fact before the parse: the
inputs and the file facts are decided here, and only the drop of a part or of a file with a
syntax error needs the parse.

**Limit.** Without a parse, a file fact also exists for a `part of` file, a file with a syntax
error and a source with no unique owner. The parity tool counts these as deferred. The text of
an OS read error differs from the Python text. A name that is not UTF-8 gives a `SnapshotError`
gap where Python gives `DartModuleError`. On Windows, `std` has no stable inode, so the check
after the open only requires a regular file.

**Measured (2026-11-11, median of 3 interleaved runs, load average about 30).** Equal on every
fixture, demo variant, the private app and the bench corpora. Discovery time, Rust (with the
sections) against Python `read_snapshot`: bench `dart-http` 28 against 31 ms, bench `flutter`
(6 623 files) 724 against 698 ms. Before `read_walked`, the real-path lookup of each file gave
2.3 against 1.2 s on `flutter`.

**Tests.** `tests/test_collector_native_dart_discovery.py`, `native/dart/src/*_tests.rs`,
`native/snapshot/src/listing_tests.rs`.
