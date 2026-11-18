# ArchKeel 5.0 release notes (draft)

> **Draft for the release owner (#716).** Do not publish as is. This draft does not approve an RC,
> tag or release. The lead finalises the text at the final release gate. Each number below names
> its source. A row marked **to confirm** needs a check on the release commit.

These notes compare ArchKeel 4.0.1 with the current development line. They describe new behavior,
breaking changes, migration steps, and known limits. They are not final release notes.

## Summary

- **One decision path.** The Rust core `archkeel-core` is the only decision path. The Python engine
  of 4.0.1 is deleted
  ([AD-432](architecture/decisions/ad-432-the-rust-core-is-the-only-decision-path.md)).
  The Python package reads the options, starts the core and prints its result.
- **Named uncertainty.** The core reports UNKNOWN when it detects incomplete evidence. This does
  not prove that every PASS is sound. Open false-PASS issue
  [#1811](https://github.com/rapiddweller/archkeel/issues/1811) has a compiled reproduction on
  `main`.
- **Exit codes follow the verdict.** Without a baseline, PASS exits 0, FAIL exits 1, and UNKNOWN
  or a refusal exits 2 for `validate` and `report`. With a baseline, exit 2 means every UNKNOWN is
  accepted; a refused run exits 1. This changes CI behavior (see
  [breaking changes](#breaking-changes-and-migration)).
- **Some 4.0.1 features are not on the current development line** (`check`, amendments, saved
  observations, focused reports, the standalone `explore` command, and Studio). The report still
  includes its Explorer. Do not treat `main` as a released 5.0 build.

## What is new

### The Rust core and its language profiles

- One core binary collects the facts of each language and decides each rule. There is no Python
  fallback.
- **Rust is a new language profile.** ArchKeel checks Cargo workspaces and single crates.
- TypeScript: each rule kind that the core has ported is decided.
- Python and Dart: the rules that read the import graph are decided, and `interface_boundary`
  ([AD-504](architecture/decisions/ad-504-the-python-survey-writes-the-publication-route-of-each-named-import.md)).
  A Dart cycle rule is also decided when the survey proves the package map is complete. Other
  unported rule kinds are UNKNOWN. The current list is in
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
- **HTML report.** `report --output PATH` writes a static page from the same ruling. The page
  includes the interactive Explorer and its architecture view: As-Is, Target and Diff. The
  standalone `explore` command is not available on `main`. Studio is also unavailable, so this is
  not a standalone Studio drill. See the [report reference](reference.md) and
  [`html_arch.rs`](../native/report/src/html_arch.rs).
- `report --topology` adds the components, modules, edges and declared structure to the JSON.
  `report --format json` writes the core frame to a file.
- **Cycles.** A cycle shows its closed path in import order, with one `file:line` for each step.
  The JSON row adds `path` and the sorted `members`
  ([AD-786](architecture/decisions/ad-786-a-cycle-row-names-its-closed-path-and-its-sorted-members.md)).
- **Premise.** When a PASS rests on a stated premise, the result prints it with the verdict (see
  [premises](#premises-that-a-pass-can-rest-on)).
- **Baselines.** `validate --baseline` can accept selected UNKNOWNs. An accepted UNKNOWN stays
  UNKNOWN. The baseline check does not turn it into PASS.

## What changes in your results

### More UNKNOWN, and why

Some cases that 4.0.1 could not see now produce a named UNKNOWN. This is not complete. A compiled
reproduction for [#1811](https://github.com/rapiddweller/archkeel/issues/1811) still gives false
PASS results for a forbidden dependency and two cycle rules on `main` `cef0d6f3a`. Independent
review evidence is recorded in
[#1824's review comment](https://github.com/rapiddweller/archkeel/pull/1824#issuecomment-6973117320).
The proposed fix in [#1842](https://github.com/rapiddweller/archkeel/pull/1842) is a draft. It is
not part of `main`.

The earlier plant and reference-project counts do not describe current `main`. The collectors and
decision path changed after those runs. Do not use those counts as release evidence. Re-run the
reference projects on the release commit before publication.

### Other changes

- A rule kind that the core has not ported gives UNKNOWN with the gap `rule_kind_not_ported`.
- A scan with `collector_argv` uses an external collector. Its facts cannot prove a rule
  ([AD-344](architecture/decisions/ad-344-only-a-producer-that-the-host-trusts-can-give-pass.md)).
- New FAILs are possible: the core can prove a violation that 4.0.1 did not see.

## Breaking changes and migration

Measured with `uvx archkeel==4.0.1` and main `edef7a140` on the same plant unless a row says otherwise.

| What | 4.0.1 | 5.0 | What to do |
|---|---|---|---|
| Exit code of a FAIL | `validate` 2, `report` 0 | 1 for both | A CI job that checks "exit 0 = pass" keeps working for PASS. Treat 1 as FAIL and 2 as "not decided or refused". |
| Exit code of an UNKNOWN | the rule could be PASS (see above) | 2 | Read the named cause. Fix the code or accept the entry in a baseline. |
| JSON result | 4.0.1 result schema | `command`, `outcome`, `status`, `exit_code`, and a core frame when a run completes | Read `status` and `exit_code`; a refusal has no frame. |
| `check` | available | refused, exit 2 | Keep 4.0.1 for `check`. |
| `validate` options `--against`, `--amendment`, `--write-amendment`, `--accept-new`, `--write-graph`, `--compact-open-decisions`, `--decided-by`, `--rationale` | available | refused by name, exit 2 | Keep 4.0.1 for these workflows. |
| `report` options `--only`, `--rule`, `--component`, `--full`, `--input`, `--baseline` | available | refused by name, exit 2 | Use `report --output` (HTML) or `--json`. |
| `init` options `--language`, `--namespace`, `--source`, `--force`, `--full`, `--tsconfig`, `--collector-argv`, `--collector-output-limit-bytes` | available | refused by name, exit 2 | Run `archkeel init`, then edit `archkeel.toml`. |
| Saved `architecture.json`, interactive reports, amendments | available | not available | No replacement on the current development line. |
| Internal shell names (`archkeel.cli.*`) | public names | 35 names got a leading underscore ([#1438](https://github.com/rapiddweller/archkeel/pull/1438), owner decision) | They were never an API. Use the command. |
| Baselines | available | `validate --baseline` and `validate --write-baseline` are available | Review a rewritten baseline before you commit it. |
| Amendments | available | not available | Keep 4.0.1 for amendment workflows. |
| Installation of the core | — | release builds carry the core in platform wheels ([AD-436](architecture/decisions/ad-436-a-platform-wheel-carries-the-core-and-no-other-wheel-is-built.md)) | Confirm the wheel set and version from the release workflow. `main` is a development build, not a release candidate. |

## Performance

The previous timing table measured an earlier core and is not evidence for current `main`.
Measure the same projects again on the release commit before publication.

## Known limits and open false-PASS classes

The full list is [known limits](known-limits.md). A false PASS occurs when the code breaks a rule
but the result is PASS. The table lists open, reproduced cases checked for this draft.

| Class | Issue |
|---|---|
| Rust: dropping an erased value from a sibling store gives false PASS for a forbidden dependency and both cycle rules. Reproduced on `main` `cef0d6f3a`; see the compiled cases in [#1824's review](https://github.com/rapiddweller/archkeel/pull/1824#issuecomment-6973117320). | [#1811](https://github.com/rapiddweller/archkeel/issues/1811) |
| Rust: a method in the file of its type, called through a field. The issue remains open; main has regression tests in `tests/test_collector_false_pass_rust_own_file_method.py`. | [#1571](https://github.com/rapiddweller/archkeel/issues/1571) |

Issue #1811 was open on GitHub when this draft was checked on 2026-11-18. Remove or update its
row if the issue closes or its reproduction changes before release.
The #1811 fix proposal in #1842 is a draft and does not change `main`. Before release, fix each
reproduced false PASS in this table and retain its regression test. Do not treat an unresolved
false PASS as accepted.

These issues were in the earlier table and are closed on GitHub:
[#1515](https://github.com/rapiddweller/archkeel/issues/1515),
[#1516](https://github.com/rapiddweller/archkeel/issues/1516),
[#1517](https://github.com/rapiddweller/archkeel/issues/1517),
[#1518](https://github.com/rapiddweller/archkeel/issues/1518),
[#1523](https://github.com/rapiddweller/archkeel/issues/1523),
[#1529](https://github.com/rapiddweller/archkeel/issues/1529) and
[#1674](https://github.com/rapiddweller/archkeel/issues/1674). Check issue status and reproductions
again on the release commit.

Other limits of 5.0:

- Python and Dart decide only the import-graph rules and `interface_boundary`. Dart cycle rules
  have a receipt when the survey proves the package map is complete.
- Rust macros: a macro that the scan does not expand is a named gap. On `pydantic-core`, unexpanded
  macros can hold the assignment rule UNKNOWN. The historical count and its source commit are not
  verified here, so this draft does not state a number.
- `explore`, `guide`, `story`, `view` and `studio` are not on the current development line. The
  report's embedded Explorer remains available.
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
