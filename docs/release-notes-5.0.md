# ArchKeel 5.0 release notes (draft)

> **Draft for the release owner (#716).** Do not publish as is. The lead finalises the text at
> release. Each number below names its source. A row marked **to confirm** needs a check on the
> release commit.

These notes are for users of ArchKeel 4.0.1. They say what is new, what changes in your results,
what breaks and how to migrate, what is faster, and what ArchKeel 5.0 does not prove yet.

## Summary

- **One decision path.** The Rust core `archkeel-core` decides every rule. The Python engine of
  4.0.1 is deleted ([AD-432](architecture/decisions/ad-432-the-rust-core-is-the-only-decision-path.md)).
  The Python package is now a thin shell: it reads the options, starts the core and prints its result.
- **More honest results.** A rule is PASS only when the core proves it. Where 4.0.1 gave PASS
  without a proof, 5.0 gives UNKNOWN and names the cause. UNKNOWN is not PASS.
- **Exit codes follow the verdict.** PASS exits 0, FAIL exits 1, UNKNOWN or a refusal exits 2, for
  `validate` and for `report`. This is a breaking change for CI jobs (see
  [breaking changes](#breaking-changes-and-migration)).
- **Faster and smaller.** On the reference project FastAPI, `validate` took 0.87 s and 31 MiB
  instead of 51.7 s and 211 MiB (see [performance](#performance)).
- **Some 4.0.1 features are not in 5.0 yet** (`check`, amendments, saved observations, focused
  reports). Each one is refused by name with exit 2 and the remedy "use release 4.0.1".

## What is new

### The Rust core and its language profiles

- One core binary collects the facts of each language and decides each rule. There is no fallback
  to Python and no partial PASS.
- **Rust is a new language profile.** ArchKeel checks Cargo workspaces and single crates.
- TypeScript: each rule kind that the core has ported is decided.
- Python and Dart: the rules that read the import graph are decided, and `interface_boundary`
  ([AD-504](architecture/decisions/ad-504-the-python-survey-writes-the-publication-route-of-each-named-import.md)).
  Every other rule of these two languages is UNKNOWN in 5.0. The current list is in
  [known limits](known-limits.md#supported-projects-on-main).
- Python target version: set `python = "3.13"` in `[scan]`, or ArchKeel takes the lowest version of
  `requires-python`. The collector supports Python 3.11 to 3.14 and runs no interpreter.

### Getting started: `init` and auto-init

- `archkeel init` drafts `archkeel.toml`, a contract and its provenance page from the folder layout
  and the manifests. It reads no source file. Every decision in the draft is a TODO
  ([AD-626](architecture/decisions/ad-626-init-drafts-open-decisions-from-the-folder-layout-and-decides-nothing.md)).
- **Auto-init.** `validate` and `report` run the draft step when `archkeel.toml` is missing. To stop
  it, use `--no-init` or set `ARCHKEEL_NO_INIT=1`.
- **Mixed repositories.** A repository with several language areas gets a system document with one
  part for each area ([AD-660](architecture/decisions/ad-660-init-drafts-a-system-for-a-mixed-repository.md)).
- **Python and Rust together.** A single Cargo crate is a Rust part. When maturin builds the crate
  with PyO3 and a Python project depends on it through a uv workspace or path source, the draft
  states the interface from the Python part to the Rust part
  ([AD-784](architecture/decisions/ad-784-a-system-draft-states-a-python-to-rust-interface-only-from-a-stated-binding.md)).
  A module name alone never makes an interface. Measured on pydantic (`e56f60fd`): three parts
  (`pydantic`, `tests`, `pydantic_core`) and the edges `pydantic -> pydantic_core` and
  `tests -> pydantic_core`.

### The system scan

- One run checks every part of a system document and gives one verdict
  ([AD-616](architecture/decisions/ad-616-exact-ports-and-one-system-run.md)).
  The report draws each part and each declared interface as a cross-part edge.

### Output

- **Text.** In a terminal, the result starts with the verdict and its exit code, then the
  violations, then the causes that hold rules. `--summary` prints at most fifteen lines for a CI
  log. `--all` lists every item. `--verbose` adds the core binary and its digest.
- **JSON.** Every result starts with `command`, `outcome`, `status` and `exit_code`
  ([AD-735](architecture/decisions/ad-735-the-draft-step-has-one-outcome-and-runs-after-the-core-is-found.md)).
  `outcome` is one of `verdict`, `collect_refused`, `command_refused`, `delivery_failed` or
  `completed`. A refusal has the field `refusal` with `kind` and `message`.
- **HTML report.** `report --output PATH` writes one static page from the same ruling. Its
  architecture section is the Explorer: As-Is, Target and Diff, with a drill-down into each part and
  component ([AD-606](architecture/decisions/ad-606-the-report-page-holds-the-4-0-1-explorer-with-the-5-0-design-tokens.md)).
  The page loads no external resource.
- `report --topology` adds the components, modules, edges and declared structure to the JSON.
  `report --format json` writes the core frame to a file.
- **Cycles.** A cycle shows its closed path in import order, with one `file:line` for each step.
  The JSON row adds `path` and the sorted `members`
  ([AD-786](architecture/decisions/ad-786-a-cycle-row-names-its-closed-path-and-its-sorted-members.md)).
- **Premise.** When a PASS rests on a stated premise, the text, the JSON field `premise` and the
  report print it with the verdict (see [premises](#premises-that-a-pass-can-rest-on)).

### Baselines

- A baseline (schema 1.4.0) can accept an UNKNOWN by its kind, subject and reason. The core compares
  the run with the file in both directions: a new entry and a stale entry are both drift
  ([AD-546](architecture/decisions/ad-546-a-baseline-accepts-an-unknown-by-what-it-is-and-the-core-compares-it-both-ways.md)).
  An accepted UNKNOWN stays UNKNOWN and never exits 0.

## What changes in your results

### More UNKNOWN, and why

4.0.1 gave PASS for some forms that it could not see. 5.0 follows one law: a wrong PASS is never
allowed, and a case that the core cannot see is a named gap. So some rules that were PASS on 4.0.1
are UNKNOWN on 5.0, each with its cause.

Measured example (a plant of three Python modules, 2026-11-17): `client.py` calls
`importlib.import_module(os.environ.get("M", "json"))`, and a rule forbids `client -> service`.

| Version | Rule | Exit (`validate`) |
|---|---|---|
| 4.0.1 | PASS | 2 (contract diagnostics) |
| 5.0 (main `edef7a140`) | UNKNOWN: the import target is computed | 2 |

With `M=app.service`, Python imports the forbidden module, so the 4.0.1 PASS was not proven.

Reference projects (gate 2, main `323f09881`, single runs on the same prepared tree):

| Project | 4.0.1 PASS/FAIL/UNKNOWN | 5.0 PASS/FAIL/UNKNOWN | Cause of the change |
|---|---|---|---|
| FastAPI 0.163.0 | 3/0/0 | 3/0/0 | Same |
| bazel_worker (dart-lang/tools) | 4/0/0 | 4/0/0 | Same |
| pydantic v2.14.3 | 5/0/0 | 1/0/4 | 95 named gaps: 48 dynamic import hazards, 30 re-export ambiguities, 10 star imports, 7 `sys.modules` changes ([#1503](https://github.com/rapiddweller/archkeel/issues/1503)) |
| graphql-js v16.15.0 | 8/0/0 | 1/0/7 | Two computed keys that can name `constructor` and write any global ([#1504](https://github.com/rapiddweller/archkeel/issues/1504)) |

These UNKNOWNs are reported uncertainty, not proven false gaps. No new false FAIL was found on
these projects. **To confirm** on the release commit.

### Other changes

- A rule kind that the core has not ported gives UNKNOWN with the gap `rule_kind_not_ported`.
- A scan with `collector_argv` (an external collector) gives at most UNKNOWN, because the host
  cannot trust its facts ([AD-344](architecture/decisions/ad-344-only-a-producer-that-the-host-trusts-can-give-pass.md)).
- New FAILs are possible: the core can prove a violation that 4.0.1 did not see.

## Breaking changes and migration

Measured with `uvx archkeel==4.0.1` and main `edef7a140` on the same plant unless a row says otherwise.

| What | 4.0.1 | 5.0 | What to do |
|---|---|---|---|
| Exit code of a FAIL | `validate` 2, `report` 0 | 1 for both | A CI job that checks "exit 0 = pass" keeps working for PASS. Treat 1 as FAIL and 2 as "not decided or refused". |
| Exit code of an UNKNOWN | the rule could be PASS (see above) | 2 | Read the named cause. Fix the code or accept the entry in a baseline. |
| JSON result | top-level keys such as `declared_rules`, `rules`, `artifact` | `command`, `outcome`, `status`, `exit_code`, `frame`, `gaps` | Read `status` and `exit_code`; the rule rows are in `frame.rules`. |
| `check` | available | refused, exit 2 | Keep 4.0.1 for `check`. |
| `validate` options `--against`, `--amendment`, `--write-amendment`, `--accept-new`, `--write-graph`, `--compact-open-decisions`, `--decided-by`, `--rationale` | available | refused by name, exit 2 | Keep 4.0.1 for these workflows. |
| `report` options `--only`, `--rule`, `--component`, `--full`, `--input`, `--baseline` | available | refused by name, exit 2 | Use `report --output` (HTML) or `--json`. |
| `init` options `--language`, `--namespace`, `--source`, `--force`, `--full`, `--tsconfig`, `--collector-argv`, `--collector-output-limit-bytes` | available | refused by name, exit 2 | Run `archkeel init`, then edit `archkeel.toml`. |
| Saved `architecture.json`, interactive reports, amendments | available | not available | No replacement in 5.0. |
| Python API `archkeel.api` | module in the package | removed | Call the `archkeel` command and read its JSON. |
| Internal shell names (`archkeel.cli.*`) | public names | 35 names got a leading underscore ([#1438](https://github.com/rapiddweller/archkeel/pull/1438), owner decision) | They were never an API. Use the command. |
| Baseline files of 4.0.1 (schema 1.0.0 to 1.3.0) | read | read; the budgets `calls_unresolved`, `typing_positions`, `untyped_private_accesses` are not measured and give exit 2 | Run `archkeel validate --write-baseline <file>` once, review the diff, commit it. |
| Exit codes under `--baseline` | — | exit 2 only for a verdict whose every UNKNOWN is accepted; a refusal or an unwritten file exits 1 ([AD-731](architecture/decisions/ad-731-under-a-baseline-only-a-verdict-exits-2.md)) | Treat 1 under `--baseline` as "the baseline gate failed". |
| Installation of the core | — | the platform wheel carries the core and its digest ([AD-436](architecture/decisions/ad-436-a-platform-wheel-carries-the-core-and-no-other-wheel-is-built.md)) | **To confirm** at release: which platforms have a wheel. |

## Performance

Gate 2 measurement, main `323f09881` against `uvx archkeel==4.0.1`, `validate` on the same prepared
tree. One run each; the machine load was not controlled, so these numbers are not a statistical
comparison. Peak RSS is the macOS `/usr/bin/time -l` maximum resident set size.

| Project | 4.0.1 time | 5.0 time | 4.0.1 peak RSS | 5.0 peak RSS |
|---|---|---|---|---|
| FastAPI 0.163.0 | 51.68 s | 0.87 s | 210.5 MiB | 31.0 MiB |
| bazel_worker | 2.58 s | 0.24 s | 75.2 MiB | 27.1 MiB |
| pydantic v2.14.3 (package only) | 107.70 s | 0.95 s | 437.6 MiB | 47.8 MiB |
| graphql-js v16.15.0 | 11.24 s | 0.95 s | 333.1 MiB | 81.7 MiB |

A larger example: the system scan of the whole pydantic repository (`e56f60fd`: the Python package,
its tests and the Rust crate `pydantic-core`) took 6.4 to 7.2 s and about 660 MB peak RSS for
`validate`, and 6.7 s and 929 MB for the HTML report (2026-11-17).

## Known limits and open false-PASS classes

The full list is [known limits](known-limits.md). The release waits for each open false-PASS class
below. A false PASS is a PASS where the code breaks the rule.

| Class | Issue |
|---|---|
| Rust: 13 anchored value and trait dispatch forms | [#1515](https://github.com/rapiddweller/archkeel/issues/1515) |
| Rust: generic bounds and supertraits hide a forbidden trait impl | [#1516](https://github.com/rapiddweller/archkeel/issues/1516) |
| Rust: a public re-export of an extern self alias hides a forbidden module | [#1517](https://github.com/rapiddweller/archkeel/issues/1517) |
| Rust: an outside registry source replacement changes a modeled derive | [#1518](https://github.com/rapiddweller/archkeel/issues/1518) |
| Rust: a method in the file of its type, called through a field | [#1571](https://github.com/rapiddweller/archkeel/issues/1571) |
| Python boundary types on 3.14: slots and an outside class write | [#1523](https://github.com/rapiddweller/archkeel/issues/1523) |
| TypeScript: an installed local package imports project source | [#1529](https://github.com/rapiddweller/archkeel/issues/1529) |
| TypeScript: a member patch of a standard global (`Math.max = f`) | [#1674](https://github.com/rapiddweller/archkeel/issues/1674) |

State on 2026-11-17. **To confirm**: this table must be empty, or each row accepted by the owner,
before the release.

Other limits of 5.0:

- Python and Dart decide only the import-graph rules and `interface_boundary`; a Dart cycle rule is
  always UNKNOWN.
- Rust macros: a macro that the scan does not expand is a named gap. On `pydantic-core` this holds
  the assignment rule UNKNOWN (20,366 named gaps, mostly `intern!` and derives).
- `explore`, `guide`, `story`, `view` and `studio` are not in 5.0.
- File output (`report --output`) needs POSIX directory handles; other platforms refuse it.

## Premises that a PASS can rest on

A premise is a statement that the core cannot check from the repository. The run prints it with the
verdict, so a PASS is never claimed without it.

- **Python** (every Python scan): "Code outside the scan roots, including test code, hands in no
  module object of the scan and writes no binding of a module or class of the scan." The survey reads
  the code of the repository outside the scan roots; a file there that writes a module of the scan
  makes the rules that read it UNKNOWN. A test file, a name built at run time from data, and code
  outside the repository (an installed package, `sitecustomize`, a `.pth` file) are covered only by
  the premise ([AD-770](architecture/decisions/ad-770-code-of-the-repository-outside-the-scan-that-writes-a-module-of-the-scan-withholds-its-routes.md)).
- **TypeScript scripts**: "code outside the scan roots hands in no global or platform object". A
  value that may be the global object blocks a proof only when the scan has a host entry; the
  premise covers code outside the scan
  ([AD-540](architecture/decisions/ad-540-an-amplifier-form-writes-a-global-only-when-the-scan-has-a-host-entry.md),
  [AD-788](architecture/decisions/ad-788-a-repository-file-outside-the-scan-roots-that-replaces-a-global-withholds-its-proof.md)).
- **TypeScript bundler mode** (opt-in, `bundler = true`): the bundler's aliases equal the tsconfig
  `paths`. ArchKeel does not verify this ([AD-260](architecture/decisions/ad-260-typescript-bundler-mode.md)).
- **Declared door reach**: a PASS under a declared reach of a door site is shown as assumed, never as
  a plain PASS ([AD-664](architecture/decisions/ad-664-a-contract-can-declare-the-reach-of-a-door-site.md)).

What a structural PASS means (not a premise, but a limit of the claim):

- A closed class scope of a UML target passes only from a member inventory that the collector states
  complete. For TypeScript the members are those that `tsc` gives the type; Python and Rust
  inventories stay partial, so such a scope stays UNKNOWN there
  ([AD-747](architecture/decisions/ad-747-a-closed-class-scope-passes-from-a-complete-member-inventory.md)).
- A bare Python class-body annotation can satisfy a UML attribute. It declares the attribute; it
  does not prove a runtime value
  ([AD-748](architecture/decisions/ad-748-a-python-annotation-declares-a-uml-attribute.md)).

## Open points for the release owner

- The version number and the release commit.
- Measure again on the release commit: the reference table, the performance table and the
  false-PASS table.
- Which platform wheels carry the core.
- Whether `docs/release-notes-5.0.md` stays in the repository or becomes only the GitHub release text.
