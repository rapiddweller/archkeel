# Python Scope Certification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Fix two reproduced false UNKNOWN receipts without weakening incomplete-scan or ownership checks.

**Architecture:** Use the parsed Python AST to identify empty modules. Derive package coverage from the file/package relationship, not dots in a basename. Preserve inventory and conservative handling of unsupported or incomplete facts.

**Tech Stack:** Existing Python 3.11+, AST, pathlib, pytest; no dependencies.

**Spec:** GitHub issues #232 and #233, with independent reproducers documented in their descriptions. Exact module ownership (#211) is a separate feature, not part of this bugfix task.

## Global Constraints

- Existing CLI/IR contracts and Dart behavior remain compatible.
- Comment-only files stay in inventory; docstrings and executable statements are not empty.
- Failed parsing, actual ownership gaps and partial scans never become PASS.
- Controller alone commits after independent QA and Astra review.

## Review Focus

- Module docstrings remain executable AST statements with an ownership obligation.
- Dotted basenames do not imply extra physical directories.
- A nested scan cannot certify an unscanned parent namespace.
- A real cycle remains FAIL beside a dotted-name file.
- Parse failures do not acquire empty-module exemptions.

## Task 1: Correct Python scope receipts

**Files:**
- Modify: `src/archkeel/analyzer/embedded/scanner.py` (empty-module facts).
- Modify: `src/archkeel/analyzer/embedded/violations.py` (`_package_paths`).
- Create: `tests/test_python_scope_certification.py` (independent QA-owned regressions).
- Update the existing release notes and scope reference only if their descriptions change.

**Interfaces:**
- Consumes: `ParsedModule.tree: ast.Module` and existing module records (`qualified_name`, `file`).
- Produces: unchanged `blank_modules: frozenset[str]` and `_package_paths(package: str, modules: Sequence[RawRecord], profile: Profile) -> frozenset[PurePosixPath]`.

- [ ] Independent Luna QA writes real observation tests: empty/comment initializers pass; docstring/import initializers remain UNKNOWN; dotted files certify complete root scans; partial scans remain UNKNOWN; cycles remain FAIL; parse errors remain incomplete.
- [ ] Run `.venv/bin/python -m pytest -q tests/test_python_scope_certification.py`; observe intended assertion failures for both reproduced bugs before production edits.
- [ ] Independent Luna implementation fixes only the two shared fact producers; no receipt bypass, source exclusion or invented module owner.
- [ ] Run the new tests and nearby receipt/cycle tests; confirm CLI JSON and generated HTML carry the same result.
- [ ] Run `UV_NO_CONFIG=true make check`, `make self-observation`, `make gate`; inspect regenerated self-observation changes. Reuse existing demo/reference files for focused positive/negative examples.
- [ ] Astra reviews the frozen diff and independent results. Controller reviews exact staging, then commits the coherent bugfix.

Release is separate: no new version claim until merged CI, tag publication and an isolated package install have passed.
