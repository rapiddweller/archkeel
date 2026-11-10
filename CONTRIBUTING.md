# Contributing to Archkeel

Thank you for helping. This page lists what a pull request needs to pass CI and review.

## Set up

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv python install 3.11.12 3.12.10
uv sync --locked
```

`.python-version` pins 3.11.12: CI runs the gate on it, and the fresh self-observation records it.
The runtime test in `make check` also starts `python3.12`, so 3.12 must be on your `PATH`.
Browser publication, Mermaid rendering and the UML TypeScript compiler check require
Node.js 22 and npm; CI installs them. `make typescript-compiler-check` runs pinned
TypeScript 5.9.3 against `fixtures/H-uml-typescript/tsconfig.json` with `--noEmit`.
This development check is separate from the Python-hosted `make typescript-native`
collector tests and the installed CLI, which do not require Node.
Dart analysis runs in Python. `make dart-test` checks it without installing a Dart SDK.
`make test` also checks the TypeScript collector's Python architecture and browser module boundaries.
Only `make flutter-demo-check`, which builds and runs the demo app, needs Flutter and Dart.

## Before you push

```bash
make ci-pr-check BASE=origin/main        # policy, lint, types and a fixed set of Core tests
make ci-pr-report-check                  # report data and JavaScript logic
```

Run `make merge-check PR=<number>` before each merge. It checks the conflicts and the changed files of the pull request, and warns when the branch is behind `main`.

Merge rules ([AD-341](docs/architecture/decisions/ad-341-ci-has-a-time-budget-and-a-test-runs-on-any-free-worker.md), updated by [AD-348](docs/architecture/decisions/ad-348-a-pr-gets-one-class-and-the-lead-dispatches-full.md), 2026-11-10):

1. One review per PR. A PR that can enable a PASS also gets the false-PASS probes (`tests/test_collector_false_pass_gate.py` in each PR, `tests/test_collector_false_pass_full.py` in Full); a probe expects UNKNOWN or FAIL, never PASS. The author fixes the findings and the lead checks the fixes. There is no second review round. A problem found later becomes a follow-up issue. The goal is a good solution, not perfection.
2. Local gate on the final head: `make ci-pr-static BASE=origin/main`, the area tests, `make native-check` when `native/` changes, `make merge-check`, and the lead's merge-tree check. Push only on a green local gate. A PR in a fix loop is a draft; a draft runs no CI.
3. Merge when the review and the local gate hold, and CI is green or 15 minutes have passed since the push, whichever comes first. No Full run per PR.
4. Do not update the branch unless the merge-tree shows a real conflict.
5. Full runs on `main` nightly, and by dispatch when useful. A failure on `main` becomes a backlog issue with a priority, and is fixed later, not at once. Exception: when `main` no longer builds locally, no agent can work, so fix it at once.
6. Run `python3 tools/ci_daily.py` for the daily line. Targets: CI at most 10 min, queue wait at most 3 min.
7. Revisit these rules when the Rust corpus is complete, or after a second red `main` of more than 1 hour.

Policy validation runs first. `BASE` also checks widenings and amendments; CI pins the PR base SHA.
Without `BASE`, the local gate validates only the checked-out policy.
Each PR runs the same fixed set of checks. The report sample checks scene/projection data and
renderer output. The selected Python tests include unit, integration and CLI tests; each test job
runs one area. Saved-report tests run in the area test jobs, not again in the report job.
The `PR_TEST_FILES` list in `tests/pr-test.mk` names this fixed set file by file and test by test;
there is no rule that selects it. `make report-browser-tests` runs the local Chromium tests; Full also runs them. Samples do not
replace testing the behavior you change. The core set runs eight whole Dart test files, one Dart
CLI smoke, one UNKNOWN safety case and five Flutter Target guards; complete Dart and Flutter
variant coverage stays in the full checks.

The scheduled **Full verification** workflow runs `make ci-core-check SKIP_TESTS=1`, which
includes the UML TypeScript compiler check. It also runs `make report-timing`, `make mermaid`,
`make report-browser-tests` and `make demos`. It runs the full suite in area jobs on Linux/Python 3.11, collector compatibility on Linux/Python 3.12, the Python compatibility
test set (`make python-compat`) on Python 3.12, 3.13 and 3.14, and one Windows/Python 3.11
safety check for process and path behavior. The compatibility set is `--selection=python-compat`
in `tests/areas.py`: each test marked `requires_python` and the listed files. A test must not read
`sys.version_info`. Mark it `@pytest.mark.requires_python(<minor>)` or `requires_python(below=<minor>)`.
If it expects one result before a version and another from that version, parametrize it with
`by_python(<minor>)` from `tests/conftest.py`. `<minor>` must be a version that Full tests.
TypeScript's Python architecture and browser module
boundaries stay in the full suite. Manual dispatch uses the same checks.
Release tags call that workflow before package build and
publication. Use `make ci BASE=origin/main` locally for the complete gate.
Jobs run on pinned images (`ubuntu-24.04`, `ubuntu-24.04-arm`, `windows-2025`, `macos-15`,
`macos-15-intel`). The Linux wheel jobs use manylinux and musllinux images pinned by digest. A move
to a new image is a deliberate change: run Full on the branch before you merge it.

Keep four workflow files: CI, Full verification, Pages and release. Use existing Make targets
or dispatch Full verification for diagnostics; do not add temporary workflows. The tested file
inventory requires an explicit reviewed change for a new workflow.

## Where things run

No job has a condition, so no job shows as skipped. Each aggregate runs `always()`: a skipped
aggregate would count as passed.

| Workflow and job | Runs on | Command to reproduce |
|---|---|---|
| CI: Lint, types and architecture | each PR | `make ci-pr-static BASE=origin/main` |
| CI: Tests: `<area>` | each PR | `make pr-test AREA="<area>"` |
| CI: Report and renderer tests | each PR | `make ci-pr-report-check` |
| CI: Docs diagrams | each PR | `make mermaid`; the job also runs `tests/test_mermaid.py` |
| CI: Demos | each PR | `make demos` |
| CI: Native: Rust checks and dependency policy | each PR | `make native-check` |
| CI: All checks passed | each PR | none: it needs every CI job and reports each job time against the budget ([AD-341](docs/architecture/decisions/ad-341-ci-has-a-time-budget-and-a-test-runs-on-any-free-worker.md)) |
| Full: Architecture, build and report checks | nightly, dispatch, release, PR that changes Full | `make ci SKIP_TESTS=1`, then `make report-browser-tests` |
| Full: Tests: `<area>` | same as above | `make full-test AREA="<area>"` |
| Full: Demos | same as above | `make demos` |
| Full: Python 3.12.10 / 3.13.15 / 3.14.7 compatibility | same as above | `make python-compat` |
| Full: Windows: collector safety | same as above | `make collector-safety` on Windows |
| Full: Linux: source collectors | same as above | `make typescript-native dart-test build smoke` |
| Full: Native wheel: `<target>` (six targets) | same as above | `make native-wheel NATIVE_TAG=<tag>` on the target |
| Full: All Full checks passed | same as above | none: it needs every Full job |
| Pages: Publish the verified report gallery | after each Full run on `main` | `make report-pages` |
| Release: Full, build, publish and gallery refresh | each version tag | `make build plugin-release VERSION=<version>` |

A red job means its command failed: run the command in the third column to reproduce it.
`tests/areas.py` puts each test file in exactly one area. CI runs the `make pr-test` selection;
Full runs all tests. A PR runs Full only if it changes what Full runs. These paths start Full:
`.github/workflows/**`, `.github/actions/**`, `.python-version`, `pyproject.toml`, `uv.lock`,
`tools/browser-runtime/package*.json`, `tests/conftest.py`, `tests/test_report_pages.py`,
`tools/report_pages.py`, `tools/report_timing.py` and `tools/full.mk`. `tools/full.mk` holds each
Make recipe that CI does not run, such as `full-test` and `python-compat`. The `Makefile`, the
`pr-test` list and `tests/areas.py` do not start Full. Tests in CI check that `tests/areas.py`
still gives each area its files, matches the Full job matrix and keeps a valid `python-compat`
selection. A change to a `Makefile` variable (`UV`, `TEST_WORKERS`) does not start Full: the
nightly run covers it. Dispatch Full on the branch to check it before you merge. Name a new test file
so that an area pattern matches it. Pages publishes only a passed Full run of the current
`main`. It uses the `make demos` and `make report-timing` output of that run, so it builds nothing
again.

The [published architecture report](https://rapiddweller.github.io/archkeel/) updates after a
successful scheduled or manual full verification on Main. Reports retain FAIL and UNKNOWN
findings; a failed build leaves the published report intact. GitHub Pages must use **GitHub
Actions** as its publishing source.

Run `make report-pages` to generate the same site in `test-artifacts/pages/`: an entry page,
the current report and the Python, Dart and TypeScript demos with shared detail pages and canonical
JSON. Demo links open in the dark theme; `/demos/` leads to the gallery.
`make demos` runs every gallery demo with the same code, checks its expected result and
prints one table. A failed demo does not stop the next one; the run fails at the end.

`make demo-uml OUTPUT=<fresh-directory>` checks the TypeScript fixture with the same
compiler before generating the Python, Dart and TypeScript UML reports.

## Browser assets

Run `make browser-graph-generate` after protocol source changes, then
`make browser-runtime-generate` after any runtime source change. The locked build
tools produce the first-party inline bundle, loaded after unchanged canonical ELK;
installed reports require no Node or network.
`make browser-graph-check browser-runtime-check browser-architecture-check`
checks generated bytes, the Flow AST witness, strict protocol consumers and native
source ports. Keep the nine browser source owners and exact contract restrictions.
A verified copy of the locked ELK package supports native import resolution; a
different existing root installation is preserved and rejected.

## Inspect the self-observation

Tests generate one fresh report per session and share it across workers. They check
coverage, architecture rules, interfaces and declared budgets against the current code.
No generated result or provenance snapshot needs to be committed.

To inspect the same repository locally:

```bash
make self-observation
```

This prints the result and writes JSON/HTML to ignored `test-artifacts/self-observation/`.
Architecture contracts, baselines and amendments remain reviewed source files.

## A behaviour change carries its decision

- **Test first.** Add the test that shows the issue, see it fail, then make it pass.
- **Record the decision.** A change in behaviour gets an `AD-<n>` file under
  [docs/architecture/decisions/](docs/architecture/decisions/) with its reason, the rejected
  alternatives, its limit and the tests that check it, an index row in
  [docs/architecture/decisions/README.md](docs/architecture/decisions/README.md). Update documents that describe
  the old behaviour. Keep the decision under the tested 70-line limit. The
  [roadmap](docs/roadmap.md) lists open work only.
- **Keep the contract true.** A new module needs a component in `architecture-contract.json`, and a
  new import between components needs a `requires` entry with its reason. Never widen a rule to
  make a check pass.
- **Keep a source file at 500 lines or less.** This covers each Python file under `src/` and each
  Rust file under `native/` and `crates/` ([AD-314](docs/architecture/decisions/ad-314-source-files-have-at-most-500-lines-and-legacy-files-only-shrink.md)).
  A split must follow a responsibility seam. A legacy file over the limit is in
  `tests/file_size_baseline.json`. It must not grow. Remove its entry when it reaches 500 lines.
- **A change in `native/` needs a Rust toolchain.** `native/rust-toolchain.toml` pins it. Run
  `make native-tools` once for the pinned `cargo-deny` and `cargo-auditable`. Then run
  `make native-check` ([AD-316](docs/architecture/decisions/ad-316-native-collectors-live-in-native-and-reply-with-protocol-8.md)).
  Without `cargo`, the native collector tests are skipped locally. CI always has `cargo`, so they
  fail there when it is missing. `make native-wheel` builds the platform wheel of your host with
  the binary and its SBOM, then installs it and runs the binary
  ([AD-317](docs/architecture/decisions/ad-317-a-platform-wheel-carries-the-native-typescript-collector.md)).
- **A performance change earns at least 10 %.** Compare the median of three interleaved runs,
  before and after, on the run the change targets (`make report-timing`, or a large repository).
  Below 10 % the change is discarded; record the measurement on the issue instead.
- **Commit messages** start with an imperative sentence and explain why in the body.
- **Rust code follows measured rules** ([AD-327](docs/architecture/decisions/ad-327-rust-architecture-rules-are-measured-in-the-gate.md)).
  A function has at most 100 lines, cognitive complexity 15, nesting 4 and 7 arguments. Nesting 4
  uses the units of clippy: the function body and an `impl` block each count as a level. A free
  function can hold 3 nested `if` blocks, and a method 2. Production
  code has no `panic!`, `unreachable!`, `todo!` or `unimplemented!`. A function over a limit carries
  `#[expect(clippy::..., reason = "...")]`; remove it when you fix the function. A new crate needs
  an entry in `native/layers.toml`. Do not add a module cycle. None exists today. `make native-report` counts
  indexing, arithmetic and `as` casts that can panic or truncate.

Contract or baseline budget widenings require a reviewed v2 amendment binding both policies. Use `make ci BASE=<base-commit>` to check them before the full gate. A changed amendment must match exactly; multiple changed records fail. After you rebase or merge main, a stale amendment (`amendment_status: stale`) needs no hand edit. Commit your work, then run `make amendment-refresh BASE=origin/main`. It rewrites only the four digests of the one amendment your branch adds or changes. It keeps `decided_by` and `rationale`. It refuses a dirty tree, a BASE that is not an ancestor of HEAD, and more than one changed amendment. The gate means "the amendment matches this diff", not "the diff is approved": read the measured changes that the command prints, and check that they match the reviewed scope of the PR. `decided_by` and `rationale` are free text, not authenticated approval. A raised budget is fine
when its rationale names the cause; never reshape code only to stay under a ratchet.

## Write in Simplified Technical English

Write issues, pull request text, commit messages, docs, decision records and code comments in
[ASD-STE100](https://www.asd-ste100.org/) (Simplified Technical English). Aim for about 80 % of
the spec. The full spec is very strict, and 80 % already makes text much easier to read. This
applies to people and to coding agents. Agents receive it through [AGENTS.md](AGENTS.md).

- Write one idea in each sentence. Steps: up to 20 words. Descriptions: up to 25 words.
- Write steps in the imperative, one action in each step, and number them.
- Use the active voice and the present tense. Use "must" for a requirement and "can" for a possibility.
- One word has one meaning. Do not use synonyms for variety. Use the same term for the same thing every time.
- Use plain words: "use", not "utilize"; "start", not "initiate". No slang, no idioms.
- Keep the articles (a, an, the). Do not stack more than three nouns.
- Put a warning before the step it affects.
- Define a technical term once. Keep command, flag and file names exact, in code font.
- Keep a paragraph to six sentences or less. Use lists and tables for facts and steps.

Before: "The collector's deadline can potentially be overridden by users who might want to
accommodate larger repositories." After: "Set `collector_timeout_seconds` to give the collector more
time on a large repository."

Do not rewrite old text only for style. New and changed text follows this standard.

## Update the agent skill

Edit [skills/archkeel/SKILL.md](skills/archkeel/SKILL.md). The CLI asset links to this source.

## Plugin files: what is where

The repository root is the plugin. There is no second copy.
- `plugin.json`: the Codex and agent-plugins manifest.
- `.claude-plugin/plugin.json`: the Claude Code manifest. Packaging requires the same version.
- `.claude-plugin/marketplace.json`, `.agents/plugins/marketplace.json`: catalogs with `source ./`.
- `skills/archkeel/SKILL.md`: the skill source. The CLI asset is a link to it.
- `docs/assets/archkeel-mark.svg`: the icon, a link to the report asset.
- `make plugin-release` builds the plugin ZIP from the root for each release tag.

## Release assets

The tag workflow automatically builds the plugin alongside the Python package.
`make plugin-release VERSION=5.0.0` sets both exported manifest versions from the tag
and verifies the ZIP and checksum under `build/plugin-release/`. Source manifests
stay unchanged; no manual version bump or later asset upload is needed.
The tag workflow owns one draft GitHub release: it verifies uploaded downloads
before PyPI publication, then publishes that same draft. Do not create a competing
release manually. Pages keeps its Main-only deployment policy: after publication,
the existing full Main workflow refreshes the gallery if the tag is still Main.
