# AD-69 One annotation is read once, for both readers

## What changes

`_resolved_position_types` reads a facade annotation the way `_boundary_type_verdict` reads it:
the bare name, and the element of a known collection. It read only bare names, so the two
readers of the same annotation disagreed the moment [AD-67](ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md)
taught the rule to enter a collection.

| Reader | `Payload` | `tuple[Payload, ...]` |
|---|---|---|
| `boundary_types` (AD-67) | judged | judged |
| reachability (AD-65), before | reached | **invisible** |
| reachability, now | reached | reached |

## Why

The combination judges a type and then calls the entry that declares it unused. Measured on this
repository, 18 types across 18 facade functions were resolved by the rule and invisible to the
reachability reading:

```python
def open_decisions(observation: Observation) -> tuple[OpenDecision, ...]: ...
#                                                     ^ judged, but never counted as reached
```

`KnownViolation`, `InterfaceEdge`, `InsideLevel`, `StructureMetric`, `HostRecord`, `RunResult`,
`Record`, `ViolationRow` and `OpenDecision` are all in that list. Declaring any of them would have
produced the `interface.unused` that [AD-65](ad-65-a-type-a-declared-facade-signature-exposes-is-a-used.md)
exists to remove, one subscript deeper.

A type inside a `list[...]` crosses the boundary exactly as the bare one does. One reading, one
helper, no second definition to keep in step.

## Rejected

| Alternative | Why not |
|---|---|
| Leave the readings apart | The drift is the defect AD-65 names, and it is measurable today: 18 types. |
| Teach reachability its own collection walk | A second definition of what an annotation exposes, which is the thing this removes. |
| Enter unions and mappings here too | AD-67 left both undecidable for the rule; the two readers must agree, so this follows it rather than overtaking it. |

## Limit

Both readers now enter one level. A nested subscript, a union, a mapping, a dotted name and a
forward reference stay unresolved on both sides, which is the point: they are unresolved
*together*. `ANALYZER_VERSION` rises to 0.30.0, because a facade function's `facade_types` record
gains the elements it always exposed.

## Check

`tests/test_analyzer.py::test_facade_types_resolve_a_collection_element` fails on the unmerged
readings: the collection element is missing from `facade_types` while `boundary_types` judges it.
`archkeel report --root .` on this repository lists `OpenDecision`, `InterfaceEdge` and the other
16 under the functions that expose them.
