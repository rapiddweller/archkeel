# Contributing to Archkeel

Thank you for helping. This page lists what a pull request needs to pass the local gate and review. CI runs on `main` only (AD-348).

## Set up

Install [uv](https://docs.astral.sh/uv/), then:

```bash
uv python install 3.11.12 3.12.10
uv sync --locked
```

`.python-version` pins 3.11.12: CI runs the gate on it. Full also runs the shell tests on 3.12.
The Rust core decides each run (AD-432), so you need a Rust toolchain: `native/rust-toolchain.toml`
pins it. Run `make core` to build `archkeel-core`. Without the core binary, `archkeel validate`
refuses with exit 2. The tests build their own core; without `cargo` they are skipped locally.
Browser code checks, Mermaid rendering and the UML TypeScript compiler check require
Node.js 22 and npm; CI installs them. `make typescript-compiler-check` runs pinned
TypeScript 5.9.3 against `fixtures/H-uml-typescript/tsconfig.json` with `--noEmit`.
Main supports Rust and TypeScript projects and the import rules of Python (AD-450) and Dart
(AD-468) projects. Use archkeel 4.0.1 for the other Python and Dart rules.
Native Python and Dart unit tests stay under `native/`. The tests that compared them with the
Python collectors are deleted; the Python collectors are gone, and a release 4.0.1 oracle is not wired.

## Before you push

```bash
make ci-pr-check BASE=origin/main        # lint, types and a fixed set of tests
```

`make pr-precheck` runs the cheap static checks in about 20 seconds: format, lint and `cargo fmt`. Run it before every push. `make pr-gate-report` (or `make pr-gate KEEP_GOING=1`) runs every step of the PR gate, cheap ones first, and prints one table of all failures with their first lines and a fix hint, so one run shows every problem. The CI gate stays fail-fast (AD-756).


Merge only when the required check `PR gate` has passed (GitHub branch protection enforces it) and the review is done. A PR that deletes a whole feature says in its text that the owner approved the deletion; no label is needed ([AD-1270](docs/architecture/decisions/ad-1270-the-merge-tools-are-deleted-and-github-enforces-the-pr-gate.md)). Never `git reset --soft` onto a moved `origin/main`: your tree is then compared with a newer main and reverts what landed in between.

Merge rules ([AD-341](docs/architecture/decisions/ad-341-ci-has-a-time-budget-and-a-test-runs-on-any-free-worker.md), updated by [AD-348](docs/architecture/decisions/ad-348-a-pr-gets-one-class-and-the-lead-dispatches-full.md), 2026-11-10):

1. One review per PR. The review checks the responsibility of each new file, module and crate against the contract (see "Keep the contract true"), and the PR text shows the dog-food run (AGENTS.md). A PR that can enable a PASS also gets the false-PASS probes (`tests/test_collector_false_pass_*.py`); a probe expects UNKNOWN or FAIL, never PASS. See "Counter-examples for a PASS". The author fixes the findings and the lead checks the fixes. There is no second review round. A problem found later becomes a follow-up issue. The goal is a good solution, not perfection.
2. Local gate on the final head: `make ci-pr-static BASE=origin/main`, the area tests, `make native-check` when `native/` changes, and the lead's merge-tree check. Push only on a green local gate.
3. Merge only on green (AD-674): the required check `PR gate` of the PR must pass; GitHub enforces it for everyone, also for admins. Three tiers: the PR gate (static checks, core build, self and system check, and main-tier tests of touched areas), the main tier (a push to `main`: the whole fast suite and `make native-check`, at most 15 minutes) and the nightly Full run (scaling, large scans, Windows and Python matrix, at most 45 minutes). AD-674 amends [AD-348](docs/architecture/decisions/ad-348-a-pr-gets-one-class-and-the-lead-dispatches-full.md).
4. Do not update the branch unless the merge-tree shows a real conflict.
5. Full runs on `main` nightly, and by dispatch when useful. A failure on `main` becomes a backlog issue with a priority, except when `main` no longer builds locally: then fix it at once, because no agent can work.
6. Run `python3 tools/ci_daily.py` for the daily line. Targets: CI at most 10 min, queue wait at most 3 min.
7. Revisit these rules when the Rust corpus is complete, or after a second red `main` of more than 1 hour.

### Counter-examples for a PASS

A false PASS destroys trust, so a PASS must be hard to get. A false FAIL or UNKNOWN makes someone look at it, so it finds itself.

- A change **can enable a PASS** when, for some input, a rule result moves from FAIL or UNKNOWN to PASS. It also can when it removes a gap, an edge or a scanned file.
- Such a change must list the **counter-examples** that the author tried. A counter-example is code that must break the PASS. The probe is the test file that holds it.
- Each counter-example needs proof that its code runs (it compiles or executes on the target toolchain) and the result UNKNOWN or FAIL.
- A counter-example that still gives PASS becomes a strict-xfail probe and a row in `docs/known-limits.md`. The PR text names it.
- The reviewer adds its own counter-examples. The author does not wait for them.
- Only a change that moves a PASS to a FAIL or an UNKNOWN needs no list. A change that moves a FAIL to an UNKNOWN needs one: with a baseline an accepted UNKNOWN exits 0 and hides a real violation.
- A false FAIL is a normal bug.

Each CI run (a push to `main`) runs the fast tests, one area in each job (`make fast-test AREA=...`).
The PR gate selects areas from changed paths with the rules of `tests/areas.py`. A native or CLI
source change runs the main-tier tests of its selected areas in parallel. A native report change
selects the CLI and report areas. Other native and CLI changes select every area. A native change
also runs `native-check`. Changes to the gate run all areas and the native check. Other changes
keep the PR-tier selection. A path that no rule names selects every area.
The slow files of `SLOW_FILES` in
`tests/areas.py` (memory, large scans) carry the marker `slow` and run only in the nightly Full run.
A requested area that holds no test after the marker filter fails. Samples do not replace testing the behavior you change.
Python import rules run through the release core in `tests/test_cli_native_python_imports.py`.
Dart import rules run through the release core in `tests/test_cli_native_dart_imports.py`.
No new recordings replace the other Dart project tests.

The scheduled **Full verification** workflow runs `make ci-core-check SKIP_TESTS=1`, which
includes the UML TypeScript compiler check. It also runs `make self-validate`. It runs the whole suite in area jobs on Linux/Python 3.11, and the shell tests
and the package check on Linux/Python 3.12. Manual dispatch uses the same checks.
Release tags call that workflow before package build and
publication. Use `make ci BASE=origin/main` locally for the complete gate.
Jobs run on pinned images (`ubuntu-24.04`, `ubuntu-24.04-arm`, `windows-2025`, `macos-15`,
`macos-15-intel`). The Linux wheel jobs use manylinux and musllinux images pinned by digest. A move
to a new image is a deliberate change. The PR needs the local gate; CI and Full on `main` check the image after the merge.

Use existing Make targets or dispatch Full verification for diagnostics; do not add temporary
workflows. A new workflow file needs the approval of the owner in its PR text (AD-1251).

## Where things run

Only `publish-gallery` has a condition (it publishes from `main` only). No other job has one, so no other job shows as skipped. Each aggregate runs `always()`: a skipped
aggregate would count as passed.

| Workflow and job | Runs on | Command to reproduce |
|---|---|---|
| CI: Lint, types and architecture | each push to `main` | `make ci-pr-static BASE=origin/main`, then `make self-validate` |
| PR gate: PR gate | each pull request | `make pr-gate` |
| CI: Tests: `<area>` | each push to `main` | `make fast-test AREA="<area>"` |
| CI: Native: Rust checks and dependency policy | each push to `main` | `make native-check` |
| Pages: Publish the report gallery | a push to `main` that changes a gallery input (AD-1223), nightly, and dispatch on `main` | `make report-gallery` |
| CI: All checks passed | each push to `main` | none: it needs every CI job and reports the time of each job ([AD-341](docs/architecture/decisions/ad-341-ci-has-a-time-budget-and-a-test-runs-on-any-free-worker.md)) |
| Full: Architecture, build and report checks | nightly, dispatch, release | `make ci-core-check SKIP_TESTS=1`, `make self-validate` |
| Full: Tests: `<area>` | same as above | `make full-test AREA="<area>"` |
| Full: Publish the latest main build | nightly and dispatch with `publish`, on `main` only | `python3 tools/publish_main_build.py` after the wheels of Full |
| Full: Linux: shell and package on Python 3.12 | same as above | `make shell-compat`, then `make build smoke` |
| Full: Native wheel: `<target>` (six targets) | same as above | `make native-wheel NATIVE_TAG=<tag>` on the target |
| Full: All Full checks passed | same as above | none: it needs every Full job |
| Release: Full, build, publish and gallery refresh | each version tag | `make build plugin-release VERSION=<version>` |

The final 5.0.0 release also checks the complete system frame with its candidate wheel
([AD-991](docs/architecture/decisions/ad-991-final-5-0-requires-the-complete-system-frame.md)).
Every declared rule must be present once and read PASS. The frame keeps each premise.
Before release, compare FastAPI and bazel_worker with 4.0.1. These comparisons are separate.
Release 4.0.1 gave PASS for FastAPI (AD-530). Release 5 gives UNKNOWN with 10 gaps, all computed or literal dunder attribute reads (AD-1053, AD-1058). This difference is expected.

A red job means its command failed: run the command in the third column to reproduce it.
`tests/areas.py` puts each test file in exactly one area. The main tier runs `make fast-test`;
Full runs all tests, on `main` nightly, by dispatch, or when a release calls it. No PR runs Full. Full covers changes to these paths, and a PR that changes them gets no run before its merge:
`.github/workflows/**`, `.github/actions/**`, `.python-version`, `pyproject.toml`, `uv.lock`,
`tools/browser-runtime/package*.json`, `tests/conftest.py` and `tools/full.mk`. `tools/full.mk`
holds each Make recipe that CI does not run, such as `full-test` and `shell-compat`. The `Makefile`, the
`tests/areas.py` do not start Full. Tests in CI check that `tests/areas.py`
still gives each area its files and matches the Full job matrix. A change to a `Makefile` variable
(`UV`, `TEST_WORKERS`) does not start Full: the nightly run covers it. Full on `main` checks it
after the merge. Name a new test file so that an area pattern matches it.

Each push to `main` that changes a gallery input publishes the report gallery to GitHub Pages
([AD-462](docs/architecture/decisions/ad-462-fixture-results-are-pinned-and-the-nightly-run-publishes-a-gallery.md)).
The job `publish-gallery` of the workflow `pages.yml` (AD-740; it ran in CI before, and a newer push cancelled it) runs `make report-gallery` and deploys `test-artifacts/gallery`. It is
not in the needs of `All checks passed`, so a Pages error never fails CI. The Pages source of the
repository must be set to GitHub Actions. The gallery has two sections: ArchKeel as one system
(`self/index.html` and its shield endpoint `self/badge.json`; the weakest verdict of the parts of
`docs/architecture/architecture-system.json`, an interim,
[AD-522](docs/architecture/decisions/ad-522-archkeel-shows-one-system-verdict-built-from-its-two-self-runs.md)),
with the reports of the Rust core, Python shell and Studio UI (one HTML file and a
shield endpoint file for each part), and the fixture table. The README links these paths, so do not rename them. `fixtures/matrix.json` states the intent of each
run (PASS, FAIL or UNKNOWN) and the issue that blocks it when the core differs; it holds no observed
count. A test fails when the core gives another status than the intent without a named blocker (AD-1261).
The Python engine built the older gallery and its Pages workflow (`pages.yml`); AD-432 deleted both.
The Windows wheel job builds and checks the wheel. It also runs the disk-root Rust tests and
`tests/test_cli_windows_root.py` through the release core. It does not run the full shell suite.

## Rust documentation and helpers

Each non-test `.rs` file under `native/` starts with a `//!` line that names its responsibility.
Each public item has a short `///` that says what it is or what it means (`missing_docs` is
`deny` for every crate). A macro that declares items takes the doc of each one from its input.

There is no central utils module. A helper lives in the component that owns its meaning. Code that
several crates share lives in the lowest crate that owns that meaning, as `pytext`, `snapshot`,
`facts` and `build-support` do. A helper that one crate uses stays in that crate. No module,
file, directory or crate is named `util`, `utils`, `common`, `helper`, `helpers`, `misc` or
`shared`.

## Browser assets

Edit the Studio TypeScript in `studio/src/`. Run `make studio-ui-generate` to build its
ES modules in `src/archkeel/cli/assets/`. Run `make studio-ui-check` to compare the shipped
files with the pinned compiler output. The installed Studio serves these files without Node.js.

## Inspect the native self-check

`make self-check` runs `make self-validate` and prints at most 40 lines from its results: the
verdicts, the violations, the largest UNKNOWN causes, files over the size limit
and near it, the import hotspots and the cycles. Run it before you change code and before you push.
Its exit code is the one of `make self-validate`. The full output is in
`test-artifacts/selfcheck/self-validate.log` ([AD-1088](docs/architecture/decisions/ad-1088-make-self-check-prints-the-first-minute-of-a-change-in-40-lines.md)).

ArchKeel checks the Rust source of `native/` with its own core (AD-432). No file lists accepted
gaps, no run is compared with an earlier run, and no label approves anything
([AD-1260](docs/architecture/decisions/ad-1260-the-self-check-gate-checks-one-run-and-compares-nothing.md)).
The README badge shows the verdict counts of main.

```bash
make self-validate-native
```

This builds the core, runs `archkeel report --config native/archkeel.toml` and prints the counts
(rules PASS, FAIL and UNKNOWN, gap records, violations). The gate is red only when the result is
missing, empty, malformed or a refusal, when the core reports a FAIL or a violation, or when the exit
code is not the one that the statuses give. An UNKNOWN rule and a gap never fail it and never turn into
a PASS. The last line is `self-check gate: GREEN` or `self-check gate: RED (exit 1)`. A FAIL or a
violation has no approval path: fix it. A new class of gaps gets a decision record. For a new
field-receiver gap, write the call as a path call (`Type::method(&value)`) or bind a typed local. The
full result is in ignored `test-artifacts/validation-native/result.json`.

`make self-validate-shell` checks the Python shell of `src/archkeel` with the contract
`docs/architecture/target/shell-contract.json` ([shell](docs/architecture/shell.md), AD-478) with the
same gate. `make self-validate` runs both checks and the system check. The system check includes the
Studio UI contract at `studio/architecture-contract.json`. The tools have no architecture contract.

## A behaviour change carries its decision

- **Test first.** Add the test that shows the issue, see it fail, then make it pass.
- **Record the decision.** A change in behaviour gets an `AD-<n>` file under
  [docs/architecture/decisions/](docs/architecture/decisions/) with its reason, the rejected
  alternatives, its limit and the tests that check it. The index is generated from the files
  (`python tools/decision_index.py`, [README](docs/architecture/decisions/README.md)): add the one file and edit no
  shared list. Update documents that describe
  the old behaviour. The
  [roadmap](docs/roadmap.md) lists open work only.
- **Keep the contract true.** A new crate or module in `native/` needs a component in
  `native/architecture-contract.json`, and a new import between components needs a `requires`
  entry with its reason. A new module in `src/archkeel/` belongs to a component of the shell contract.
  Its first docstring or `//!` line names one
  responsibility, and no `forbidden_responsibilities` item of its component applies to it.
  Never widen a rule to make a check pass.
- **Keep a source file near 500 lines or less.** `make self-check` prints the sizes (AD-1088). No test
  fails on size (owner decision 2026-11-27). A split must follow a responsibility seam.
- **A change in `native/` needs a Rust toolchain.** `native/rust-toolchain.toml` pins it. Run
  `make native-tools` once for the pinned `cargo-deny` and `cargo-auditable`. Then run
  `make native-check` ([AD-316](docs/architecture/decisions/ad-316-native-collectors-live-in-native-and-reply-with-protocol-8.md)).
  Without `cargo`, the native tests are skipped locally. CI always has `cargo`, so they
  fail there when it is missing. `make native-wheel` builds the platform wheel of your host with
  the core and its SBOM, then installs it alone and reads the verdicts of its core
  ([AD-436](docs/architecture/decisions/ad-436-a-platform-wheel-carries-the-core-and-no-other-wheel-is-built.md)).
- **A performance change earns at least 10 %.** Compare the median of three interleaved runs,
   before and after, on the supported project that the change targets.
  Below 10 % the change is discarded; record the measurement on the issue instead.
- **Commit messages** start with an imperative sentence and explain why in the body.
- **Rust code follows measured rules** ([AD-327](docs/architecture/decisions/ad-327-rust-architecture-rules-are-measured-in-the-gate.md)).
  A function has at most 100 lines, cognitive complexity 15, nesting 4 and 7 arguments. Nesting 4
  uses the units of clippy: the function body and an `impl` block each count as a level. A free
  function can hold 3 nested `if` blocks, and a method 2. Production
  code has no `panic!`, `unreachable!`, `todo!` or `unimplemented!`. A function over a limit carries
  `#[expect(clippy::..., reason = "...")]`; remove it when you fix the function. A new crate or module needs
  a component in `native/architecture-contract.json`. Do not add a module cycle (the contract
  rule `NATIVE-NO-MODULE-CYCLES` fails). `make native-report` counts
  indexing, arithmetic and `as` casts that can panic or truncate.

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
release manually. After publication, the tag workflow starts Full verification on Main if the tag is still Main.
