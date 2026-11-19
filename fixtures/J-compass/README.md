# Compass architecture Target

This fixture preserves the `compass_app/app` Dart source from Flutter samples at commit [`5541c59ab8e9d7e74c1a35ef22bd43a487fc596c`](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app/app). The Target is independently authored from that source and the upstream [Compass overview](https://github.com/flutter/samples/blob/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app/README.md).

The layout is the one of flutter/samples: the app is `compass_app/app/` and the scan root is `compass_app/app/lib`. The fixture holds the Dart source of the app and the 37 `pubspec.yaml` files of the pub workspace (the root and every member, as listed in the root `workspace:`), at their upstream paths. No other source of flutter/samples is included. The core reads the workspace from these manifests (AD-808).

Read [the Target map](docs/target.md) for the complete responsibilities, ownership, principal APIs and evidence limits. The source is BSD-3-Clause licensed (Copyright The Chromium Authors); the licence text is preserved in `LICENSE`; `SNAPSHOT.json` records physical input provenance.

## Supplemental pinned web build

Install Flutter `3.44.8` with Dart `3.12.2`. The [toolchain pin](compass-build/toolchain.json)
records the tested macOS arm64 SDK archive URL and SHA-256, plus the framework and engine
revisions. Use a fresh output directory for each run.

```sh
make compass-pinned-build
```

The build fetches the full upstream workspace at the source pin and checks every file in
`SNAPSHOT.json`. The [workspace lockfile](compass-build/pubspec.lock) pins 199 hosted
package archives by SHA-256. Flutter enforces those hashes in a fresh package cache.
Eight SDK packages come from the pinned toolchain. The remaining Git package, `menubar`,
has a resolved commit in the lockfile and an independently checked archive SHA-256.
This lockfile records a supplemental resolution. The upstream source pin has no lockfile.

The web bundle and `build-evidence.json` go under `test-artifacts/compass-pinned-build`.
Set `COMPASS_BUILD_OUT` to a fresh directory for a replay. The evidence gives web output
digests and Dart analyzer definitions for the ten fields whose types are undecided in
the source-only ArchKeel report. Verification covers compilation and package resolution.
