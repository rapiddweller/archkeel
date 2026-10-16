# Typed State Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** State facts and their parser use owned nominal control types while preserving existing wire values and event order.
**Architecture:** State vocabulary belongs to state_facts; state_codec owns its event tag. Convert raw JSON once; evaluate nominal facts and collect them directly.
**Tech Stack:** Python 3.11, StrEnum, frozen dataclasses, native Archkeel source observation, pytest, Ruff, mypy.
**Spec:** User instruction on #542 includes parser/protocol string comparisons without parser exception.

## Global Constraints

- Preserve JSON keys, values, event order and malformed-input rejection.
- Keep StateFacts and the nominal StateEvent union; add no general-purpose enum.
- Native own budgets stay unknown_positions <= 65 and calls_unresolved <= 919.
- Module/name/path identities remain string data.
- Remote branches and hosted checks provide isolation; no executor operations.

## Review Focus

- All enum members round-trip to historical wire text.
- Unknown/non-string tags fail with ValueError.
- Mutation paths need two segments; reads/writes need one.
- Fixed authored Target catches widening a public control field to str.
- Parser equality/membership/match/string-alias probes produce native violations.

### Task 1: State vocabulary and wire boundary

**Files:** ir/state_facts.py, ir/state_codec.py, check/evaluation/state.py, analyzer/python/state.py and necessary producers; tests/test_typed_state_protocol.py; IR/root contracts, Makefile and docs.
**Interfaces:** FieldState uses BindingState, ReferentMutability, ObjectMutability and PropertyAssignment; AttributeAccess.access uses StateAccess. Codec owns EventKind assignment/attribute/pass.

- [x] Add nominal API, exact wire, invalid-tag and native Target/guard mutation tests.
- [x] Run hosted RED on unchanged production.
- [x] Implement owned enums, enum constructor decoding, collector and evaluator changes; serialize exact values.
- [ ] Add type ports, independent Target field annotations and guard for state facts and codec.
- [x] Run focused native/state/collection tests, Ruff, mypy, hygiene and own baseline validation.
- [ ] Hand clean file map and evidence to parent for independent Astra review and integration.
