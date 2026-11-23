# AD-1063 The PR gate fetches the real projects when a change can alter their result

**Status.** Accepted (lead decision, 2026-11-23). It amends [AD-462](ad-462-fixture-results-are-pinned-and-the-nightly-run-publishes-a-gallery.md) and the CI part of [AD-1060](ad-1060-the-pages-run-can-be-rerun-and-the-gates-say-what-they-prove.md).

**Reason.** The fixtures `N-fastapi-realworld` and `O-bazel-worker-realworld` need the network. Only the nightly run fetched them. So #1968 turned the real FastAPI pin from PASS to UNKNOWN (10 gaps), and no PR gate showed it.

**Decision.**
1. The job `Tests: CLI and core` of a pull request runs `python3 tools/select_areas.py --fetch <base>`. The answer is `fetch` when a changed path is under `native/` or `fixtures/`, or is one of `FETCH_FILES` in `tests/areas.py` (the fixture tools, the matrix test and the workflow itself).
2. On `fetch`, the job restores `test-artifacts/source-cache` with the key of `pages.yml` (`gallery-sources-<hash of fixtures/*/SOURCE.json>`) and sets `ARCHKEEL_FETCH_SOURCES=1` and `ARCHKEEL_SOURCE_CACHE`. In no other case does the workflow set them.
3. A push to `main` and a PR without these paths stay offline. The nightly run keeps the fetch.
4. `fixture_source.checkout` waits 5 s and 15 s between its three attempts. A failed fetch raises `SourceError` with its reason, and the matrix test fails. The test never skips a fetch that was asked for.

**Cost.** A PR that fetches adds about 90 s to the CLI job on a cache miss (the run of the 3 network tests), and less on a hit. The cache comes from the Pages run on `main`.

**Limit.** The Python collector no longer exists; its paths are not in the list. A change in `src/archkeel/cli/` does not fetch. A host outage fails the job after about 20 s of waiting.

**Tests.** `tests/test_cli_fetch_sources_gate.py` (the path rule, the selector and the workflow wiring), `tests/test_report_gallery_sources.py` (the waits).
