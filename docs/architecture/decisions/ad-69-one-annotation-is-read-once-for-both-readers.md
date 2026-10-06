# AD-69 One annotation is read once, for both readers

## What changes

`_boundary_type_verdict` owns annotation reading. Its `_Position` carries resolved
types; `_resolved_position_types` reuses them for exposure instead of resolving
bare names separately ([AD-67](ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md)).

| Reader | `Payload` | `tuple[Payload, ...]` |
|---|---|---|
| `boundary_types` (AD-67) | judged | judged |
| reachability (AD-65), before | reached | **invisible** |
| reachability, now | reached | reached |

## Why

Eighteen types across eighteen self facade functions were judged but not reached:

```python
def open_decisions(observation: Observation) -> tuple[OpenDecision, ...]: ...
#                                                     ^ judged, but never counted as reached
```

Declaring those types could still yield `interface.unused`, recreating
[AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md)'s conflict inside
collections. One walk keeps judgments and usage consistent.

## Rejected

Separate collection walks already failed review; copies drift when only one gains
a shape. Do not add unions or mappings to exposure ahead of rule resolution.

## Limit

Both readers enter one level. Nested subscripts, unions, mappings, dotted names
and forward references remain unresolved together. Exposure receives the contract
because it uses the verdict walk, though resolution itself does not depend on it.
Analyzer version rises to 0.30.0 for collection elements; merging readers adds no
further byte changes on a fixed sample.

## Check

`test_facade_types_resolve_a_collection_element` catches the old mismatch.
Structural tests require one `_resolve_named_type` caller and forbid a separate
exposure collection walk. A nine-shape parity test includes unresolved cases.
