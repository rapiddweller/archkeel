# AD-740 The gallery is published by its own workflow

**Status.** Accepted. Part of #880 (lead request of 2026-11-17). Visible change: the published report follows main within one successful publish run.

**Reason.** `https://rapiddweller.github.io/archkeel/self/` showed commit `12d22faa3` while main was far ahead. The job `publish-gallery` ran inside `ci.yml`. Since AD-736's one-run-per-branch rule (#1421) a newer push cancels the running CI, and merges arrive every few minutes against a run of 8 minutes: 38 of the last 40 CI runs on main were cancelled, and the publish job with them.

**Decision.** `pages.yml` holds the job. It runs on a push to main, nightly (03:47 UTC) and by dispatch. No workflow-level concurrency group cancels it; the job group `github-pages` has `cancel-in-progress: false`, so GitHub lets the running publish finish and keeps one pending run, the newest. The nightly run repairs a failed publish within a day. The job keeps `continue-on-error`, outside every aggregate.

**Rejected.** `cancel-in-progress: false` on the whole of `ci.yml` (queues the gate behind old runs); publishing only from the nightly Full run (the site would be a day behind).

**Tests.** `tests/test_gallery_publication.py`.
