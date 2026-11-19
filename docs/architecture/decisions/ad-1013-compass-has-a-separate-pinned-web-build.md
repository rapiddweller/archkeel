# AD-1013 Compass has a separate pinned web build

**Status.** Proposed.

**Decision.** Build the complete upstream workspace at the Compass source pin. Use a separate
workspace lockfile and a fresh package cache. Flutter must enforce the lockfile and match the
framework, engine and Dart SDK revisions in the build pin. Verify the Git package archive
by SHA-256. Keep the original ArchKeel scan separate.

The build writes the web bundle and an evidence report outside the tracked sources. The Dart
analyzer resolves the ten field types in that build. Each result names the exact definition
and its file digest.

**Reason.** The upstream workspace has dependency constraints but no lockfile. The source-only
collector records external dependencies and does not read their declarations. A locked build
can provide compiler evidence without changing what the source-only rule can prove.

**Limits.** The build does not run the app or check callback execution. It records the
compiler evidence separately from the ArchKeel verdict. The published hashes do not promise
that different build hosts emit identical bundles.

**Rejected.** Resolve a floating package cache during the original scan. Its package versions
could change independently of the pinned app source.

**Checks.** Run `make compass-pinned-build`. The entry point checks the source manifest,
lockfile, Git package, web output and analyzer definitions before it writes its evidence.
