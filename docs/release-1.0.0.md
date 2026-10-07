# Release 1.0.0 readiness

Scope: stabilize the existing CLI, public API and wire interfaces. Complete Dart UML,
own Target authoring and new structural port checks are follow-up work.
Release notes reconcile all 39 issues closed since 0.9.0 with merged changes.

## Before publishing

1. Review the [1.x compatibility policy](reference.md#compatibility-in-1x) and
   [0.9.0 migration](../RELEASE_NOTES.md#upgrade-from-090). Incompatible JSON/protocol
   changes also require a new package major; analyzer corrections may change findings.
2. Finalize the notes, remove the Unreleased marker, and pass local
   `make gate BASE=origin/main`, `make report-browser` and `make report-timing`.
   Verify wheel, sdist and plugin metadata for 1.0.0.
3. Merge the reviewed preparation and verify **full Main CI on that exact commit**,
   including Windows/Python 3.11/3.12 and native TypeScript jobs. Short PR CI is insufficient.
4. After release approval, tag that exact verified commit `1.0.0`.
   Tags own the Python package version; no source version constant is needed.
5. Verify the tag publication job, install the published wheel/sdist, and attach the
   versioned plugin ZIP to the GitHub release. Publication and directory listing are separate.

The tag workflow runs `make release-check`, not the complete Main/browser/platform gates.
It must not be used as a substitute for step 3.

## Remaining stabilization

| Priority | Disposition |
| --- | --- |
| Before tag | Full checks of the final release commit and published-artifact verification. |
| Recommended follow-up, #402 | Existing-draft `validate --json` still materializes all open pairs (39 components: 1,482 pairs, about 1.13 MB in the issue reproduction). Correct but costly for agents; compact init does not fix this path. |
| Acceptance, #339/#348 | Native TypeScript UML and demos are delivered, but the full language acceptance issues remain open. Do not claim compiler parity or complete coverage. |
| Human evidence, #384/#236 | Hint calibration, reviewer pilot and public-directory acceptance remain unverified. They do not establish a runtime defect. |
| Deferred, #340/#347/#356 | Complete own Target, Dart inner UML and structural-port extensions are outside this release scope. |
| Historical, #357 | The physical split is merged; historical move-only parity cannot be certified. No second split is justified. |

## Preparation evidence

- Base: `dd67a1d6c3b58ddc724964ae0e5982f9f0443a50`, after 0.9.0.
- [Full Main CI](https://github.com/rapiddweller/archkeel/actions/runs/37623893417)
  passed on that base, including the platform matrices. It does not cover this preparation diff.
- Fresh local policy check: 0 violations, 53 UNKNOWN positions, 720 unresolved calls;
  aggregate declared rules remain UNKNOWN. No policy or budget was relaxed.
- LOCAL VERIFIED: `make gate BASE=origin/main` passed: 6,034 tests, 278 skips,
  lint, typecheck, policy, build and installed wheel/sdist smoke checks. Skips are
  263 Playwright cases (covered by the separate browser target), 13 Python 3.12-only
  cases and two Linux filename cases. The single warning comes from the intentional
  duplicate-ZIP rejection fixture.
- Local 1.0.0 wheel/sdist builds and installed smokes passed using
  `SETUPTOOLS_SCM_PRETEND_VERSION=1.0.0 make build smoke`; no Git tag was needed.
  Wheel metadata says Stable and includes schemas and native TypeScript. The plugin ZIP
  has matching 1.0.0 manifests and the canonical skill. These are unpublished candidates.
- `make report-browser`: 635 tests passed; the browser artifact generator completed.
  All Playwright cases skipped by the core target are selected by this target.
- `make report-timing`: 30.86 s against 90 s on macOS/Python 3.11.12, with no
  parallel tests. Output 31,066,807 bytes against the 34,571,652-byte guard; both passed.
- Required remote verification: full Main CI on the final preparation/merge commit, tag
  publication and a fresh PyPI installation. The linked base run does not cover the preparation diff.
