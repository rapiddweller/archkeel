# AD-462 Fixture results are pinned and the nightly run publishes a gallery

**Status.** Proposed. Part of #880. This extends AD-422, AD-432 and AD-440.

**Amended.** The README showcase (#880) moves the job `publish-gallery` from Full to CI, where it runs on
each push to `main` and on a dispatch on `main`. Point 5 reads as follows: the job has the condition
`github.ref == 'refs/heads/main'`, `continue-on-error: true` and no `needs`, and it is not in the needs of
`All checks passed`. Full has no Pages permission. `make report-gallery` is in the `Makefile`. The gallery adds a
first section with two self runs (Rust core, Python shell) at the stable paths `self/core.html`, `self/shell.html`,
their `.json` files and the shield files `self/core-badge.json`, `self/shell-badge.json`. A written file names the
repository `<repo>`. The job runs on its own runner, in parallel to the other jobs. Estimate: about 5 minutes (the core build
took 2 min 19 s in CI; `make report-gallery` took 32 s on a laptop).

**Amended.** The product page (#880) makes `index.html` of the site the entry "ArchKeel as a product":
one card for the Python shell and one for the Rust core, each from its own self run, with the process
boundary drawn between them as a stated relation that no frame checks, and the verdict block of each part
with its exceptions as links into `self/shell.html` and `self/core.html` (only ids that the written report
holds: `#x<n>`, `#violations`, `#arch`). The page has no joint verdict: its heading names the worst status of
the two runs. Every count, name and state comes from the two envelopes (rule rows, `topology`,
`explain.cycles`, `details`, `collection_gaps`); the tool asks the core for the topology in one more
run whose file it throws away, so the published `.json` files do not change. The fixture table moves to
`showcase/index.html`. The page uses the files of AD-496 (fonts, tokens, theme script) and is at most 4,000
visible characters (`tests/test_report_product_page.py`). Point 3 reads: the tool writes `index.html` (the
product page) and `showcase/index.html` (the fixture table).

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
