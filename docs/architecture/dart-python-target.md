# Dart collector target

User decision, 2026-10-09: define the Target before implementation; analyze Dart
without installing or invoking the Dart SDK. This supersedes AD-211's runtime
choice. [Machine-readable Target](contracts/dart.json) owns component permissions,
module responsibilities and the principal UML types, fields and operations.

```
entry -> collect -> snapshot
                 -> parse
                 -> resolve -> snapshot + parse
```

- **entry:** shared stdin/stdout protocol; no language logic.
- **collect:** SourceFacts, records, evidence, coverage and provenance.
- **snapshot:** bounded bytes and digests; pubspec identity is separate from namespace.
- **parse:** Tree-sitter only; immutable syntax values; no filesystem or Target access.
- **resolve:** selected library/part ownership and bounded lexical bindings; no AST objects.

Use the existing Tree-sitter runtime and pinned `tree-sitter-dart==0.1.0` wheels.
Do not copy the TypeScript collector or introduce an adapter framework. The parser
package is MIT; its version participates in collector provenance. Installation and
analysis require Python, with no Node, Dart, Flutter, pub-get or compiler command.

The process port, SourceFacts schema and Dart profile remain shared and unchanged.
Runtime provenance now names Python. The collector never reads contracts or verdicts.
Sources, pubspec and every resolver input must be inside the selected snapshot,
regular files and digested. No package-cache discovery or source execution.

Keep declarations, members, signatures, visibility, enums, mixins, aliases, literal
imports/exports, parts and proven local relationships. Resolve prefixes, combinators,
lexical shadowing and local inheritance from source evidence. A constructor must
exist before a construction resolves. Field-formal and inherited constructor
parameters require a unique source declaration; otherwise keep them incomplete.
Dynamic dispatch, missing external packages, ambiguous bindings, unsupported syntax
and incomplete inventories remain UNKNOWN. Never use a global short-name match or
turn a parse error into an empty, complete file.

Tree-sitter parses syntax; it does not validate the complete Dart language or prove
runtime behavior. Language-version constraints and unsupported constructs must be
reported honestly. Existing semantic assertions and the independent H/I/J demo
Targets remain acceptance criteria; do not weaken them to make the migration green.

The UML Target fixes the principal boundaries and fields. Helper functions are open;
component ownership and allowed imports are closed. Any necessary boundary change
must update this Target before implementing it.

Acceptance: real CLI and installed wheel/sdist operate with Dart absent; existing
Dart semantic, URI, containment and demo tests pass without SDK-related skips;
Python/TypeScript behavior stays intact. Remove native collector/setup code and SDK
CI matrices only with their replacement tests. Keep cross-platform Python coverage
in the existing matrix and full browser/gallery proof in nightly/release verification.

Parser sources: [Python package](https://pypi.org/project/tree-sitter-dart/0.1.0/),
[upstream grammar](https://github.com/UserNobody14/tree-sitter-dart).
