# Source section and scalar consumer types

Part of #542. Approved slice, based on `7cfe1298fb285dfb5c53c1b8f829207ce05b7e97`.

Keep one source section vocabulary (`facts.SourceSectionName`, re-exported as `profiles.ObservedSection`) and the existing `profiles.UnmeasurableScalar`. Collectors and the wire decoder already produce these values. Preserve their types through ScanResult, validation, coverage and measurement consumers.

1. Author the real ScanResult field and three section-parameter Targets; select the durable tests in Make. Test canonical ScanResult ingress, strict wrong-domain/raw-string controls, real Target weakening and an exact-owner native string-control mutation. Run RED before product changes.
2. Narrow the four existing ports, canonicalize legacy supported ScanResult section strings once in its constructor, and migrate the 31 audited consumer predicates in six modules. Update existing section-key tables and callers; no new enum, parser, DTO, module, policy inventory or consumer conversions.
3. Run focused/native/strict checks and affected profile, nullable-measurement, ratchet, collection and graph regressions. Run normal read-only self validation without budget changes. Replay retained fixture facts through old/new Core and accept only source digest differences. Root owns combined full and Main validation.

Generic Observation sections, Record.kind, Analyzer.name, JSON keys and source-defined names stay open. Topology levels, structure levels and Python public_name visibility remain separate work.

Ruling: the local execution environment cannot fork; use an isolated Git branch and pinned read-only hosted verification instead of local worktree scripts. Parent requires bounded tests here and owns the combined full suite.

Progress:
- Analysis: exact retained artifact rows joined to 31 distinct current owner/AST sites in six modules (run 38998618074/job 117296587329). Counts are sites, not defects.

- RED: run38999235380/job117298426074: 14 expected failures, 1 pass; actual product strict144 and both authored Target schemas passed. The first attempt stopped before tests because rg was absent; it is not RED evidence.
- Legacy ingress: ScanResult is explicitly published by TARGET-EVALUATION. It previously accepted source section strings; preserve all eight supported spellings and normalize once in its constructor. The only existing direct test constructor uses an empty set. Unsupported source-only sections remain outside this port; generic Observation sections remain open.

- GREEN: run38999413354/job117298961349: all15 focused tests pass, including the real native guard, four actual Target annotation mutations, and canonical plus five strict negative controls. Product strict144 and both actual Target schemas pass. Three formatter-only product corrections follow that run; final bounded regressions and compatibility are pending.
