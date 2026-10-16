# Shared dependency selection

The `dependency-policy` component owns closed selector vocabulary and pure
module selection in `archkeel.ir.dependency`. `SelectorMatch` and
`DependencyTargetKind` are enums; `DependencySelector`,
`ModuleSelection` and `DependencySelection` are immutable named values.

Module names, package prefixes, symbols and component identities remain string
data. The contract codec converts wire values to the owned types and rejects
unsupported modes. `parse_dependency_selector` applies the same conversion to
declaration records. Core evaluates rules and produces receipts; report
projections consume selections and Core findings. A report does not decide a
different interpretation of a dependency rule.

A legacy module rule with both selectors at their prefix defaults can decide a
whole component pair when each named package has one owner. Its selection then
includes every package and exact module of those components, independently of
their display labels. Ambiguous package ownership, exact selectors, symbol
selectors and explicit import namespaces retain literal module selections and
cannot acquire whole-component intent.

Each projection prepares typed selectors once for its declarations, rather than
decoding modes for every import cell. Source/target selections carry named fields;
iteration preserves the previous helper-unpacking behavior. Existing model
exports delegate to this owner for compatibility. There is one ownership matcher,
not a second report-specific implementation.

The wire grammar, default serialization and version gates remain unchanged.
The pure policy module imports only the common dotted-name matcher from source
facts; it does not decode JSON, observe source, produce verdicts or render reports.
Its public list names the shared types and ownership matcher explicitly.
