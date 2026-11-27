# AD-1223 The main build is nightly, Pages follows its inputs, and the gate has no rerun workflow

**Status.** Accepted. Owner decision of 2026-11-27. Amends AD-824, AD-863, AD-740 and AD-1221 (point 4).

**Reason.** Measured runs a day: Latest main build 11, Pages 17, PR gate rerun 6. Each run costs 10 to 25
minutes of runners. The main build is a rolling preview, and the nightly Full run already builds the same six wheels.

**Decision.**
1. `pr-gate-rerun.yml` is deleted. After the label `ratchet-lead` the lead runs `gh run rerun <id>` for the
   latest PR gate run of the head. After a base change, push or reopen the PR.
2. A push to `main` no longer starts `main-build.yml`. The job `publish-main-build` of `full-verification.yml`
   downloads the wheels of the one nightly build and publishes them (schedule, or dispatch with `publish`). A run that can publish has its own concurrency group and never cancels, so a check run by dispatch cannot stop a
   publication. A tag run of the release skips it. The release caller gives `contents: write` as the cap. `main-build.yml` stays as
   a manual path (dispatch with `publish`) and builds its own wheels.
3. `pages.yml` starts on a push only when a gallery input changes: `native/`, `src/`, `studio/`, `schema/`,
   `docs/` (not `docs/architecture/decisions/`), `fixtures/`, `tools/`, `.archkeel/`, `Makefile`, `pyproject.toml`, `uv.lock` or the workflow. The paths
   come from `tools/report_gallery.py` (the scanned trees and the matrix) and the core build. The nightly run and
   the dispatch stay. `cancel-in-progress` stays false: GitHub advises it for Pages, and a waiting run is already
   replaced by the newest one.

**Rejected.** A schedule in `main-build.yml`: it builds the six wheels a second time each night. Deleting
`main-build.yml`: a manual publish would need the whole 40-minute Full run.

**Limit.** The path filter saves little: of 51 pushes to `main` on 2026-11-26, 39 change a gallery input (decision records, tests and other workflows are the rest). The saving of Pages comes mostly from the replacement of a waiting run. The main build is up to a day old. A publish needs only the wheels of Full to pass, not the other Full
jobs. `publish-main-build` and `main-build.yml` repeat the publish steps.

**Tests.** `tests/test_main_build.py`, `tests/test_gallery_publication.py`, `tests/test_native_ci.py`, `tests/test_make_gate.py`.
