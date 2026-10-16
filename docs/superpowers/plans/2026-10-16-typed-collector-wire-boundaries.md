# Typed collector wire boundaries implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** Give collector protocol vocabulary one typed owner and preserve canonical wire compatibility while eliminating literal parser/protocol controls in migrated modules.
**Architecture:** Facts own shared language, runtime state, and dirty-sentinel vocabulary. Protocol owns envelope versions. Codecs own private import-target/type-shape wire tags and schema field grammar, mapping once into existing immutable nominal domain values. Runtime facades reexport shared language.
**Tech Stack:** Python 3.11+, StrEnum, frozen dataclasses, pytest, native Archkeel checks on GitHub Actions.
**Spec:** Issue #542 expanded user requirement: parser/protocol string comparisons are forbidden too.

## Global constraints
- Preserve v1/v2/v3 wire bytes, errors, source unknown semantics, open profile-owned Record.kind and existing safety tests.
- No string-valued Final aliases, imported constants or .value controls to evade guard.
- Keep unresolved calls at or below the inherited baseline; ratchet genuine UNKNOWN reductions without allowances. The final stack predecessor owns a 918-call ceiling.
- Parent integrates shared contract, exact authored Target, module ports and guard deltas.
- Remote GitHub isolation only because executor cannot fork.

## Review focus
- Malformed non-string vocabulary values remain diagnosed, not accepted by truthiness/coercion.
- Legacy version roundtrips remain byte canonical and runtime-state/version gates remain strict.
- Existing nominal unions determine domain branches; wire tags are codec-private.
- Raw open payload record kinds remain data.
- Runtime facade imports remain compatible and both language definitions become one owner.

### Task 1: Typed protocol and shared facts
- [ ] Add failing tests asserting decoded language/version/state identity, malformed inputs, legacy wire bytes and runtime reexport identity.
- [ ] Run hosted RED tests on unchanged production.
- [ ] Implement owned enums and single runtime-state conversion; migrate necessary consumers.
- [ ] Run protocol/facts/runtime/type-shape tests, mypy and Ruff.

### Task 2: Typed codec control grammar
- [ ] Add native literal equality/membership/match/alias mutation guard and authored field-type weakening control.
- [ ] Migrate private wire discriminators and codec field grammar; preserve domain unions.
- [ ] Run native source controls, existing safety/conformance tests and own native baseline.
- [ ] Return clean intended commit and explicit shared-contract deltas for independent Astra review.
