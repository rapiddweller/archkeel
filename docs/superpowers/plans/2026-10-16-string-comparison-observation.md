# Bounded string-comparison observation implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for this bounded task. Steps use checkbox syntax.

**Goal:** Extend native Python syntactic comparison observations to direct bytes, named literal collections, explicit enum value extraction and the interpreter entry protocol without granting runtime type or binding proof.

**Architecture:** Keep construct observation in its existing owner. Reuse static AST binding evidence only where this collector can establish the written literal vocabulary; leave arbitrary names and dynamic/imported runtime values unclassified. Do not alter compiler receipts, namespace saturation or native proof algorithms.

**Tech Stack:** Python 3.11+, ast, pytest, hosted GitHub Actions.
**Spec:** User clarification on issue #542: parser/protocol strings are included; owned enum identity and arbitrary name data are allowed.

## Global constraints
- Remote GitHub isolation only; no local executor.
- No allowances, baseline increase, cross-module runtime inference or new external dependencies.
- Independent native FAIL controls and enum/data PASS controls; document unsupported forms honestly.

## Review focus
- Function parameters/local bindings shadow module constants: must not infer the module literal.
- Reassigned or dynamically constructed values: no false literal evidence.
- Enum member identity is legitimate; explicit string-valued member.value is a raw-value comparison.
- Mapping patterns are structure and remain excluded.
- Imported values without self-contained immutable proof remain explicitly outside guarantee.

### Task 1: Native observation and enforcement
**Files:** Modify src/archkeel/analyzer/python/constructs.py; create tests/test_string_comparison_observation.py; amend existing exclusions tests only for newly intended bytes/main semantics; document docs/architecture/string-comparison-observation.md.
**Consumes:** collect_constructs(parsed: Sequence[ParsedModule], evidence) and native observe/evaluation.
**Produces:** existing string_literal_compare records and trace-valid forbidden_construct violations; no new record schema.
- [x] Add actual-source cases for equality, membership, match, Final, named literal tuple/set/list, bytes, local Enum.member.value, main guard, parameter/local shadowing and dynamic/imported limits.
- [x] Run hosted focused tests before production edits; verify expected missing observations.
- [x] Implement bounded AST classification, preserving the existing construct owner and one record per statement.
- [x] Run focused collector, trust-boundary, import/source-binding regressions; ruff/mypy/hygiene; native self-validation with 65 unknown positions and 919 unresolved calls unchanged.
- [x] Report clean product commit, exact coverage/limits and red/green evidence for independent Astra review.
