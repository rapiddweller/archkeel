# Typed Python Property Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace property-proof string dispatch with a shared immutable domain type without changing proof outcomes or wire bytes.

**Architecture:** IR facts owns PropertyBinding, PropertyOperation and PropertyOrigin and one RecordData/Mapping decoder. Source produces nominal bindings and the existing codec writes their four-field wire form; Core decodes each method binding before sorting and dispatch. The legacy private Source TypedDict remains unchanged.

**Tech Stack:** Python 3.11+, dataclasses, Enum, pytest, native Archkeel Target/guards, Ruff, mypy; isolated remote GitHub branch and hosted Actions.

**Spec:** [typed-python-properties.md](../../architecture/typed-python-properties.md), authorized property sub-scope of #542; base `0e3b8a7f62b9b13417cda78e11b52d0de82986cd`.

## Global Constraints

- Only property operation/origin controls; no other Python vocabulary stages.
- Preserve descriptor/order/proof algorithms, malformed-wire rejection and native PASS/FAIL/UNKNOWN behavior.
- Retain source._PropertyBinding as a real dict constructor, mapping input and keyword input included.
- No Dict subclass, converter framework, inferred Target, historical JSON, baseline increase or guard-budget increase.
- facts.py must not import facts_codec or facts_validation; wire version and JSON shape remain unchanged.
- Independent final Astra and combined regression belong to the parent before merge.

## Review Focus

- Same-named setter parameters, reordered local operations and inherited base accessors keep existing source ownership.
- Shadowed/custom/decorated/async or rebound descriptors never gain proof.
- Bool/nonpositive/future lines and invalid operation/origin combinations remain rejected.
- Legacy dict indexing, unpacking, JSON and equality remain valid.
- Only scoped Source/Core property functions lose raw dispatch; unresolved/PARTIAL targets, multiplicities and UNKNOWN IDs must be measured.

---

### Task 1: Pin the consumed contract and establish RED

**Files:** new typed-properties specification/plan, tests/test_typed_python_properties.py; docs/architecture/contracts/{ir,python}.json.

**Interfaces:** PropertyBinding.operation: PropertyOperation; .source: PropertyOrigin; .line/.source_line: int. property_binding(value: RecordData | Mapping[str, object]) -> PropertyBinding; property_binding_data(binding: PropertyBinding) -> RawData. property_bindings(module, parent) -> dict[FunctionNode, PropertyBinding].

- [ ] Add nominal owner/field and actual producer Target declarations independently of implementation.
- [ ] Add real native positive Target checks, annotation-widening mutations and existing facts guard raw-dispatch mutations.
- [ ] Add scoped actual Source/Core observations and actual source-to-wire-to-Core lifecycle tests with legacy dict controls.
- [ ] Run hosted pytest against unchanged production; inspect expected assertion failures, not collection errors.

### Task 2: Implement the single property boundary

**Files:** src/archkeel/ir/{facts,facts_codec,facts_validation}.py; src/archkeel/analyzer/python/source.py; src/archkeel/check/evaluation/boundary_types.py.

- [ ] Add frozen PropertyBinding and nominal enums to facts, with the existing strict four-field decoder/order validation.
- [ ] Add only a wire writer to facts_codec, and consume the facts decoder during property coherence validation.
- [ ] Produce PropertyBinding in Source, classify decorator attribute once, serialize at method_decorator_data.
- [ ] Decode Core method bindings once into typed pairs before sorting; preserve all existing proof branches.
- [ ] Run focused property/protocol/native tests, Ruff, mypy and exact property wire comparisons.

### Task 3: Verify and freeze a reviewable carrier

**Files:** docs/architecture/decisions/issue-542-properties-amendment.json; this plan's evidence.

- [ ] Generate an amendment through the normal writer, then replay; preserve all ceilings.
- [ ] Compare native unresolved and PARTIAL sites including target lists/multiplicity and UNKNOWN identities against the exact base.
- [ ] Export and apply formatter changes; rerun relevant checks after fixes.
- [ ] Freeze a clean branch without auxiliary workflows and send evidence to the parent for independent Astra and full integration regression.

## Execution

Native execution was explicitly assigned by the parent after the preceding design review. Remote GitHub branches provide isolation because the local executor cannot fork; all tests run in hosted GitHub Actions. No additional approval pause is required.
