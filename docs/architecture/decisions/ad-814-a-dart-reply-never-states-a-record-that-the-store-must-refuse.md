# AD-814 A Dart reply never states a record that the store must refuse

**Status.** Accepted. Part of #880, closes #1706.

**Reason.** The store refused the whole dart-lang/tools system run (43 Dart parts) because of two
parts:
- `sse`: the repository has no root `pubspec.yaml`, so the survey knew no own package. Then
  `package:sse/src/server/sse_handler.dart` gave the external module `sse.src.server.sse_handler`,
  which is also the module of the scanned file in the namespace `sse`. The store refused: "observed
  local module cannot be an external target".
- `boring` (`sdk: ^3.13.3`): under an SDK that the collector does not support, the symbol records
  of its classes had no member inventories, as 4.0.1 dropped them. The facts require them: "missing
  field `member_inventories`".

**Decision.**
1. An import whose external or `dart:` module is also the module of a selected source is a gap of
   its library (`DartUnsupportedUri`, at the directive). Its message names the module. It gives no
   target (`native/dart/src/import_survey/edges.rs`, `Index::is_module`).
2. A class record always keeps its two member inventories. Under an unsupported SDK constraint they
   are partial, with the reason "the SDK constraint of the package is not supported"
   (`native/dart/src/collection/inventories.rs`). The SDK gap of the discovery stays.

AD-808 (nearest `pubspec.yaml` above the scan roots) already gives `sse` its own package. Rule 1
covers the cases that remain: no `pubspec.yaml` at all, scan roots in two packages, and a
namespace that names another package or `dart`.

**Plants.** In `tests/test_cli_native_dart_packages.py`, each one first refused by the store:
- no `pubspec.yaml`, and a `pubspec.yaml` of another name: `package:shop/b.dart` in the namespace
  `shop`;
- `dart:async` in the namespace `dart` beside `lib/async.dart`;
- a class under `sdk: ^3.13.3`.

Each now gives a verdict with the gap. Collector test:
`an_external_module_with_the_name_of_a_scanned_module_is_a_gap`.

**Effect.** dart-lang/tools at ddda9d8, `archkeel init`, `archkeel validate`: before, REFUSED in
the parts `sse` and `boring`. Now FAIL with 12 violations of the drafted contract, in 6.7 s.
