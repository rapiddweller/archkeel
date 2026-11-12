# AD-387 The native Dart collector checks SDK support before record assembly

**Status.** Accepted. Epic #880, PR 8 slice 4a. It follows AD-369 and AD-376.

**Decision.** Port `_Collection._sdk_constraints` and its constraint helpers from
`analyzer/dart/collect.py`. This layer gives a support flag and at most one exact gap.
The discovery already reads the pubspec. The parse already gives the syntax and its gaps.
The records component calls this layer after the snapshot problems, as Python does.

**Python rules and oddities, ported literally.**
1. A missing requirement keeps support true. An invalid requirement gives a gap.
2. A declared requirement with no value has its own gap message.
3. Accept only a caret or a list of comparisons. Bare versions and unions are malformed.
4. A comparison list permits adjacent comparisons, optional commas and Unicode white space.
5. Versions have one through three decimal components. Missing components become zero.
   Python `\d` accepts Unicode decimal digits. Read their values from the oracle table.
6. Ignore the prerelease and build suffix when comparing versions. Do not apply semver rules.
7. A caret sets an inclusive floor and an exclusive ceiling at the next nonzero component.
8. Keep the tightest bounds. Equal bounds keep the intersection of their inclusive flags.
9. An exclusive floor stays at the written version. Do not increment it.
10. No lower bound or an empty intersection gives the same unproven-support gap.
11. Check only the major and minor of the floor against 2.12 through 3.12, inclusive.
    An upper bound beyond parser support is not a gap. A patch number does not change support.
12. Write `SdkConstraintError` at pubspec line 1 with no evidence. The pubspec is not a source.

**Stricter cases, a closed list.**
- *SdkConstraintWorkLimit:* each input scan, copied decimal and bound comparison costs work.
  More than 1 048 576 units gives an SDK gap and support false. No partial result is supported.
  The review case `">=3,<4 " * 20000` gives this gap; Python proves support with no gap.
- *SdkConstraintDigitLimit:* more than 4 300 digits in one component gives an SDK gap.
  Python raises `ValueError` at this limit. Leading zeros count. Native never truncates a number.
  The review case `">=" + "0" * 4301 + "3.12"` checks the Python error and the named native gap.

**Cut and remaining work.** Slice 4b must assemble the symbols, imports, bases, calls,
references, bindings, inventories, duplicates, source coverage and final facts. It must use the
support flag to remove inventories. It must also check language overrides after library ownership.
The port of `resolve.py` must decide URI targets, part owners, visible names, constructor
targets and inherited formals. This slice changes no resolution, definition walk or member walk.
The store still refuses a Dart reply. This slice cannot enable a native PASS.

**Rejected.** Port discovery again: it already exists. Port declarations first: constructors
need resolution and would cross the slice boundary. Add a YAML or semver library: Python uses
neither. Use machine integers: Python accepts decimal components larger than a machine word.

**Limits.** The test-only dump exposes the support layer, not a collector reply. The parity
tool compares the Python function boundary without running resolution or the slow syntax walk.
The hostile filesystem checks also name the existing 4 MiB source limit of AD-365.
The Windows snapshot limit of AD-369 stays open. No Python production behavior changes.

**Measured (2026-11-12, Python 3.11.12, Unicode 14).** Equal SDK checks: four fixtures,
22 demo variants, private Dart 1 pubspec, dart-http 17 pubspecs and Flutter 142 pubspecs.
Hostile metadata: 42 equal, four named SDK limits. Hostile filesystem snapshots: 41 equal,
four named SDK limits and one named source size limit. Generated constraints: 3 000 equal.

**Tests.** `tests/test_collector_native_dart_sdk.py`, the Rust SDK tests and
`tools/dart_sdk_parity.py` compare the flag and exact gap records. Generated long constraints
check the work limit within ten seconds. The input `>=3.12.0 <4` costs exactly 86 units.
