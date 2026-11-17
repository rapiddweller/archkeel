# Compass architecture Target

This fixture preserves the `compass_app/app` Dart source from Flutter samples at commit [`5541c59ab8e9d7e74c1a35ef22bd43a487fc596c`](https://github.com/flutter/samples/tree/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app/app). The Target is independently authored from that source and the upstream [Compass overview](https://github.com/flutter/samples/blob/5541c59ab8e9d7e74c1a35ef22bd43a487fc596c/compass_app/README.md).

The layout is the one of flutter/samples: the app is `compass_app/app/` and the scan root is `compass_app/app/lib`. The fixture holds the Dart source of the app and the 37 `pubspec.yaml` files of the pub workspace (the root and every member, as listed in the root `workspace:`), at their upstream paths. No other source of flutter/samples is included. The core reads the workspace from these manifests (AD-808).

Read [the Target map](docs/target.md) for the complete responsibilities, ownership, principal APIs and evidence limits. The source is BSD-3-Clause licensed (Copyright The Chromium Authors); the licence text is preserved in `LICENSE`; `SNAPSHOT.json` records physical input provenance.
