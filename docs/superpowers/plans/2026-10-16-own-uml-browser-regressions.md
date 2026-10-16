# Own UML browser regression plan

The Graph/Version integration at 5933ffbbfd588ac96e36748de937cb1f6e739655 exposes three existing browser assertions: overlapping Target/Diff reference routes and a stale As-Is ArchitectureGraph method count. Full regression run 38950883561/job117141648337 establishes RED before this change.

- [x] Reproduce the two reference-route failures with actual own-report geometry and print scale, endpoints and complete overlap pairs.
- [x] Distinguish geometry defects from stale expectations; preserve visible endpoints, connected focus, unchanged evidence and route hit/line equality.
- [x] Prove the exact ArchitectureGraph method set. Compared with 7b2a14de58eb18be716c8eadef5c43928ec464a5, only __post_init__ and _validate_classifier_relationship were added to the prior eight methods.
- [x] Make the smallest routing correction supported by the geometry; do not hide edges or weaken overlap/readability assertions.
- [x] Run affected Chromium scenarios in Target, Diff and As-Is, including member previews and focus transitions.
- [x] Freeze a separate carrier with no Badge, shared-owner or policy-budget changes for Root integration and independent review.

Use existing asset ownership: report-layout owns route geometry, flow owns presentation/interaction, and tests distinguish authored Target members from observed implementation members. No broad layout rewrite, allowances, warning exemptions or historical JSON snapshots.

The scene producer requests 16 world-pixel edge clearance for existing direct UML scopes; component/package layouts retain the 10-pixel default. The request is part of the layout cache identity. The layout adapter serializes this numeric presentation input into ELK options without inferring entity kinds.

Evidence: actual three-scenario RED in run 38957990131; request/default API RED in run 38959989528; 21 Chromium/native-source/asset checks pass in run 38960252295/job117173212296. Target and Diff each retain all 21 reference routes with zero overlap pairs at scale 0.2543. Clean candidate Ruff, mypy (139 files), hygiene (11 tests) and empty formatting diff pass in run 38960446204/job117173868055. Source is frozen at df0985713d57fa103c03b6659a34a863d322a39d; subsequent carrier changes only this plan.
