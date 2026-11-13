# AD-432 The Rust core is the only decision path

**Status.** Accepted by lead decisions L-131 and L-138. Part of #880.
It supersedes the stage-1 parts of AD-399 and AD-406 and the opt-in switch of AD-422.
AD-422 stays the record of the core-only path: frame, exit table, lookup and refusals.

**Decision.**
1. Delete the Python core: `archkeel.ir`, `archkeel.check`, `archkeel.analyzer`, and each module,
   tool, fixture script and test that works only with them.
2. `validate` and `report` (text and JSON) run through `archkeel-core` with no switch.
   `--core-only` and its environment variable stay as accepted options without effect.
   `--native-core` is a removed option; the shell refuses it by name. No dual path remains.
3. PASS, FAIL and UNKNOWN give exit 0, 1 and 2 for `validate` and for `report`.
   A refusal gives exit 2. Nothing gives PASS or exit 0 that the core did not prove.
4. `check`, `explore`, `init`, `guide`, `story`, `view` and `studio` stay registered.
   Each gives the typed refusal `not_on_this_development_line`, exit 2, with the tracking issue.
   Release 4.0.1 has `check` and `init`, so their remedy is "use release 4.0.1". No release has
   the other five commands, and the refusal says so. `check` names each check it cannot run (#1103).
   There is no fallback and no success stub. `skill install` stays, because it copies one file.
5. The Python shell parses arguments, reads the config location, finds the binary, reads the frame,
   prints text or JSON and maps the exit code. It does not read facts, contracts or verdict logic.
   `tests/test_ir_owners.py` holds the closed list of shell modules.
6. The frame reader compares the root, the contract SHA-256, and a stated Git head and dirty state
   with the frame. The rule rows are trusted to the located binary. The lookup reads only the
   package directory or its checkout, never the scanned project, the current directory or `PATH`.
7. Build output: below a directory with a valid `CACHEDIR.TAG`, the survey charges the depth,
   no file bytes, and the entries to a budget of their own of 1,000,000. The used build directory
   of this repository alone has more entries than the source budget of 100,000.
   The survey selects no source, so the rule cannot hide source.
   A source that a module path selects below such a directory is collected or gives UNKNOWN.
8. The 11 rule kinds without a port keep the typed UNKNOWN of the core. This change ports no rule
   and does not change `native/model` or `native/eval`.
9. The self-check is the product path: `make self-validate-native` runs `archkeel validate` on
   `native/` and compares the result with `native/expected-gaps.json`. The browser assets and the
   Studio UI are checked the same way; the Studio UI result is pinned with one typed UNKNOWN.
10. The browser vocabularies have their TypeScript files as the only source. No Python generates them.
11. Delete the dual run of Python against the core, its tools, its corpus tests and its CI jobs.
    No Python engine remains to compare with. The Rust `dual-run` subcommand stays untouched.
12. Delete the root self-contract of the Python tree with its baseline, accepted list and UML
    contracts, and the Pages workflow, which published reports that this line cannot make.

**Reason.** Two engines gave two verdict paths and most of the maintenance work.
One path with typed refusals is smaller and cannot disagree with itself.

**Rejected.** A Python fallback for refused commands: it would give verdicts that the core did not
prove. Success stubs for refused commands. Porting reports or rule kinds in the same change.

**Limits.** No platform wheel carries the core yet. An installed package refuses each command
with `core_binary_not_found`, exit 2. The wheel hook still bundles only the two collector binaries.
Reports as HTML, `architecture.json`, explore, Studio and the merge gate `check` need ports.
Python and Dart projects stay unsupported (AD-430). Release 4.0.1 has `check`, `init`, full
reports and Python, Dart and TypeScript projects. It has no Rust profile, explore or Studio.
A tree with more than 100,000 entries outside its tagged directories, or more than 1,000,000
below them, is refused by name. A module path into a tagged directory gives UNKNOWN with the
coverage refusal of the store. The trust limits of AD-422 for Git configuration and binary
freshness stay.

**Way back.** `git revert` of the squash commit of this change restores the Python core, the
stage-1 switch and the deleted tests and tools. No data migration is necessary.

**Tests.** `tests/test_cli_core_only_exit_table.py` checks the exit table of the default path, each
refused command and the import guard. `tests/test_cli_core_only_build_output.py` plants sources in
build output. `tests/test_ir_owners.py` checks that the deleted packages do not exist.
`tests/test_native_self_core_rows.py` and `tests/test_native_expected_gaps.py` check the pinned
self-check. `tests/test_make_gate.py` checks that a refusal or an empty result fails the gates.
