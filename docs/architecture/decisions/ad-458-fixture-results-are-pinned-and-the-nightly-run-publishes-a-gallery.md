# AD-458 Fixture results are pinned and the nightly run publishes a gallery

**Status.** Proposed. Part of #880. This extends AD-422, AD-432 and AD-440.

**Decision.**
1. `fixtures/matrix.json` is the table of every project under `fixtures/`. One key is one fixture directory.
   Each key has one language and one or more runs. A run has a name, a root, an optional config,
   the contract paths and the result that the core gives today.
2. The pinned result is the exit code, the project verdict, the PASS, FAIL and UNKNOWN rule counts,
   the scope text, the gap kinds and the refusal kind and message, or no refusal.
   A project that the core refuses is pinned as refused with its exact reason.
   When a collector starts to serve it, the test fails and the author updates the pin in the same change.
   The table shows the progress. Do not weaken a pinned verdict to make the test pass.
3. `tools/report_gallery.py` runs `archkeel report --output` for each run, as HTML and as JSON.
   It reads the envelope of the CLI and writes `index.html`: fixture, language, verdict, counts, gaps,
   links, commit and build time. A refused run shows `refused: <reason>`. A link exists only for a file
   that the CLI wrote. A run without an envelope gets a row and exit code 1. The tool decides nothing.
4. `make report-gallery` builds the gallery in `test-artifacts/gallery`. It lives in `tools/full.mk`.
5. The job `publish-gallery` of Full verification builds the gallery and deploys it with GitHub Pages
   (`actions/upload-pages-artifact`, `actions/deploy-pages`, pinned by commit). It runs only for the
   schedule and for a dispatch on `main`. It is the only job with a condition and the only job with
   `pages: write` and `id-token: write`. The job is not in the needs of `All Full checks passed` and has
   `continue-on-error: true`. A Pages setting that is off, or a failed deploy, never changes the Full verdict.
6. `release.yml` gives its called Full run the same upper limit for permissions, because a called job
   cannot ask for more than its caller gives. The condition of the job is false for a release call.

**Reason.** The goal is that each fixture runs through the core again and that people can see the
nightly state. The first gallery was built by the Python engine (`tools/report_pages.py`, commit
`45746a6dd`) and published at `https://rapiddweller.github.io/archkeel/demos/` by `pages.yml`
(commit `c6ffffd5e`). Commit `5cbf811ad` deleted both. A pinned table shows which project runs.

**Rejected.** A new workflow file (the inventory allows three). A deploy that needs a green Full run
(an old Python verdict would then hide the table). A shell that rewrites the verdict for the page.
Copying output of release 4.0.1 into the repository.

**Limits.** The matrix pins the core, not a goal. An UNKNOWN verdict is pinned as UNKNOWN. The
repository setting Pages source must be GitHub Actions; the job cannot set it. The first deploy
replaces the last site of the Python engine. The report is static: no topology, no filter.

**Tests.** `tests/test_cli_fixture_matrix.py` (directory listing equals keys, language and contract
follow the config, the release core gives each pin), `tests/test_report_gallery.py` (index rows,
refused row without a link, escaping, exit code) and `tests/test_gallery_publication.py`
(job outside the verdict, condition, permissions, order, release caller limit).
