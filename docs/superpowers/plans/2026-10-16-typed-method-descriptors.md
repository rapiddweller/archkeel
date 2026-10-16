# Typed Method Descriptor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Share nominal method kinds and Python descriptor proof without changing wire data or receiver semantics.

**Architecture:** facts.py owns five-valued MethodKind and frozen MethodDescriptor. Source produces the typed descriptor; facts_codec writes the old dict, and Core/graph/validators consume one conservative scalar decoder. Arbitrary provider identities remain keys in one Source data table.

**Tech Stack:** Python3.11+, Enum, frozen dataclasses, pytest/native Target and guard mutations, Ruff/mypy; isolated remote GitHub branch and hosted Actions.

**Spec:** [typed-method-descriptors.md](../../architecture/typed-method-descriptors.md); approved base `4493b0a944e6caf0c56802c6333d9fd0090041b4`.

## Global Constraints

- MethodKind has instance/static/class/constructor/factory; no global Python-only three-value validation.
- Existing method_decorator_data returns real dicts with unchanged keys/values and keyword calls.
- No schema/protocol tightening, parameter/visibility/DefinitionContext/typing-role scope, provider enum or converter/tuple framework.
- Missing/future/off-shape wire tags remain data; no new INSTANCE/UNKNOWN/reject fallback or resolver authority.
- Property never resets a preceding STATIC/CLASS effect; descriptor counts and proof predicates are unchanged.
- No budget increase; preserve independent source-grammar work by changing only this isolated base's focused hunks.
- Parent owns final independent Astra review and combined full regression before merge.

## Review Focus

- Multiple/transparent/called/custom decorators preserve exact previous descriptor order and proof.
- Alias/shadowing and module/class rebinding never gain provider proof.
- Unknown tags, JSON null/numbers/bools/arrays/objects and missing keys keep wire compatibility and existing receiver behavior.
- Dart constructor/factory and TypeScript method tags remain valid with unchanged graph modifiers.
- Legacy dict/kwargs/JSON behavior and exact Python/TS/Dart wire bytes remain valid.

---

### Task 1: Author consumed ports and establish actual RED

**Files:** this plan/spec; tests/test_typed_method_descriptors.py; docs/architecture/contracts/{ir,python}.json.

**Interfaces:** MethodDescriptor.method_kind:MethodKind; signature_decorators_proven/source_final_method_binding:bool; property_binding:PropertyBinding|None. parse_method_kind(value:JsonValue | RawJson | MethodKind)->MethodKind|None; method_descriptor(module,node,parent)->MethodDescriptor; method_descriptor_data(descriptor:MethodDescriptor)->RawData.

- [ ] Add independent Target entities for the DTO, fields, decoder, writer and actual Source return.
- [ ] Add nominal Source/strict DTO/native annotation mutation RED tests and actual scoped dispatch observations.
- [ ] Add baseline compatibility controls for decorator ordering, receiver selection, graph modifiers and opaque wire tags.
- [ ] Run hosted RED; inspect expected assertions without collection/fixture errors, and commit.

### Task 2: Implement only descriptor controls

**Files:** src/archkeel/ir/{facts,facts_codec,facts_validation,source_graph}.py; src/archkeel/analyzer/python/source.py; src/archkeel/check/evaluation/boundary_types.py.

- [ ] Add nominal enum/DTO and conservative reader in facts without a codec import.
- [ ] Add thin writer preserving property-field omission; keep old Source raw port as wrapper.
- [ ] Convert Source proof consumers to descriptor fields and one provider identity table, retaining proof/order.
- [ ] Convert only method-kind decisions in Core/graph/property/Dart validation to the same nominal reader.
- [ ] Run new and existing method/property/protocol/native tests, exact wire checks, Ruff/mypy.

### Task 3: Freeze measured evidence for independent review

**Files:** this plan's evidence; normally generated amendment, with only resolved baseline debt ratcheted if needed.

- [ ] Run normal writer and NoWrite/replay without --accept-new or increased budgets.
- [ ] Compare unresolved/PARTIAL sites, targets, multiplicity and full UNKNOWN payloads against the exact base.
- [ ] Export/apply formatting; freeze a clean carrier without hosted verification workflows.
- [ ] Hand off exact SHA/blob/run evidence for independent Astra and parent full integration regression.

## Execution ledger

Native execution is explicitly authorized after the read-only design. Remote branches substitute for local worktrees because the executor cannot fork; hosted Actions run all checks. The plan is the durable ledger.
Pre-flight: Task2 consumes Task1's exact nominal fields/ports; names and signatures agree. Legacy Source writer and optional property omission are shared constraints, not a second decision authority.

Port correction after actual native measurement: the initially authored object input
added one object_annotation signal (52→53). The approved input domain is the existing
raw/frozen JSON value types plus MethodKind. Move the existing RawJson definition to
facts and preserve facts_codec.RawJson as the identical public reexport. Add an
independent Target parameter constraint and establish RED before this correction.
No measurement policy, ceiling, wire validation or conservative None behavior changes.
