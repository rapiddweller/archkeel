# Own UML browser regression plan

The Graph/Version integration at 5933ffbbfd588ac96e36748de937cb1f6e739655 exposes three existing browser assertions: overlapping Target/Diff reference routes and a stale As-Is ArchitectureGraph method count. Full regression run 38950883561/job117141648337 establishes RED before this change.

- [ ] Reproduce the two reference-route failures with actual own-report geometry and print scale, endpoints and complete overlap pairs.
- [ ] Distinguish geometry defects from stale expectations; preserve visible endpoints, connected focus, unchanged evidence and route hit/line equality.
- [ ] Prove the exact ArchitectureGraph method set. Compared with 7b2a14de58eb18be716c8eadef5c43928ec464a5, only __post_init__ and _validate_classifier_relationship were added to the prior eight methods.
- [ ] Make the smallest routing correction supported by the geometry; do not hide edges or weaken overlap/readability assertions.
- [ ] Run affected Chromium scenarios in Target, Diff and As-Is, including member previews and focus transitions.
- [ ] Freeze a separate carrier with no Badge, shared-owner or policy-budget changes for Root integration and independent review.

Use existing asset ownership: report-layout owns route geometry, flow owns presentation/interaction, and tests distinguish authored Target members from observed implementation members. No broad layout rewrite, allowances, warning exemptions or historical JSON snapshots.
