# CI repair and test reduction

Main `27ba8277` passed reduced PR checks, but Full run `39917947462` failed
in two Chromium tests. Repair run `40064537053` still failed at the final
`#flow-data` read after the tested interactions succeeded.

**Decisions, 24 October:** Keep tests with clear value. CI checks logic, contracts
and generated report data. Retain three short local browser smokes; review visual
changes in the Nightly gallery. Run the full collector compatibility matrix only
in Nightly, manual Full verification and Release.

- Remove 380 browser cases and the screenshot/proof generator.
- Move 26 data/projection/layout cases to Node, retaining their assertions.
- Keep local findings, keyboard navigation and unsafe-content escaping smokes;
  exclude them before fixture setup in CI.
- Keep Linux logic tests and Windows collector safety in PRs. Require the full
  collector matrix outside PRs; accept its intentional skip only in PRs.
- Generate and publish the gallery only on scheduled/manual Main runs.
- Require Full acceptance for infrastructure changes through Actions `check`;
  Main requires that check on an up-to-date branch before merging.
- Replace the repeated full-gallery pytest build with six real language/status
  samples, full-index checks and invalid-comparison controls. Full gallery stays
  in scheduled/manual publication.
- Keep native collector work stealing and 20-minute Full job limits.

**Local evidence:** Three browser smokes pass in 3.50 s. The report logic target
passes 121 tests in 45.54 s; the 39 scene/protocol/layout tests alone pass in
13.22 s, including real compiler-negative controls. CI gate/selection checks,
lint and type checks pass. All remaining tests collect; 15,330 logic cases and
three local browser cases remain.

**CI evidence:** Revision `8976ee97` passed all required checks in 16:47; the
fast PR path took 9:54. Full suite: 15,271 passed, 59 Python-3.12 skips. Its
remaining gallery test took 336.63 s. The bounded gallery test now passes locally
in 3.19 s (previous local full-gallery build: 130.87 s).

**Pending:** CI after the bounded gallery-test change. Browser rendering regressions beyond the
three smokes require manual review; platform-specific collector regressions may
first appear in Nightly. Do not merge before required checks pass.
