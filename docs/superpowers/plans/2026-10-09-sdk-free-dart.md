# SDK-free Dart implementation plan

> Use Superpowers subagent-driven-development with Luna implementers and independent review.

**Goal:** analyze Dart through the Python installation, without a Dart SDK.
**Architecture:** five responsibilities in the authored [Target](../../architecture/dart-python-target.md).
**Stack:** Python 3.11+, existing Tree-sitter 0.26, pinned Dart grammar 0.1.0.

Constraints: no legacy backend; unchanged shared protocol/Core policy; no demo-specific
logic; preserve current semantic assertions, input containment and UNKNOWN evidence.
The user authorized implementation, review, push, merge and 1.1.0 after verification.

- [x] **1. Target first.** Validate `contracts/dart.json`, inspect its UML graph and
  independently review responsibilities, dependency direction and acceptance. Commit
  the Target before product code. Probe the candidate grammar against H/I/J and modern
  Dart syntax in isolation; reject a parser that silently hides unsupported syntax.
- [x] **2. Syntax.** Add `dart/parse.py`: `parse(content: bytes) -> Syntax`; frozen
  `Span`, `Definition`, `Directive`, `Site`, `Concern`, `Syntax`. Only this module
  touches Tree-sitter. Add focused failing tests, then declarations/member/site
  extraction with real spans and explicit errors. Do not evaluate bindings here.
- [x] **3. Snapshot and resolution.** Add `dart/snapshot.py` and `dart/resolve.py`:
  `read_snapshot(request: CollectionRequest) -> Snapshot`; `Source`, `Snapshot`;
  `Resolver(snapshot, syntax)`, `module_for(rel_path)`, `resolve_name(rel_path, name)`.
  Test escapes, symlinks, module collisions, parts, combinators, prefixes, aliases,
  shadowing, inherited signatures and unresolved constructors before implementing.
- [x] **4. Collection.** Add `dart/collect.py`, replace `entry.py`; keep
  `collect(request: CollectionRequest) -> SourceFacts`. Adapt process helpers to
  Python first and retain semantic expectations. Verify the 20 independent H Target
  relationships, Flutter/Compass facts, duplicate/incomplete inventories and exact
  source evidence. Add an absent-Dart regression; include parser version in provenance.
- [x] **5. Remove SDK machinery.** Delete `dart/native`, `dart/setup.py`, setup script
  entry and SDK Make targets. Use one `make dart-test`; share Python matrix coverage
  with TypeScript. Remove SDK setup from CI and the SDK matrix, update aggregate and
  workflow assertions. Retain installed package and cross-platform checks.
- [ ] **6. Finish.** Update current docs and 1.1.0 notes. Run targeted checks, lint,
  types, build/install smokes, architecture gate and relevant broader tests locally.
  Review, fix findings, commit/push, then merge with green required CI. Publish only
  after final release verification and inspect the published artifacts.

Review risks: syntax recovery mistaken for complete input; external names mistaken
for local bindings; parts read outside selection; wrong inferred constructor/default
facts; wheel availability and SDK-dependent skips masking missing platform coverage.
