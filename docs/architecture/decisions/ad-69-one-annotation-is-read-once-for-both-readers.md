# AD-69 One annotation is read once, for both readers

## What changes

`_boundary_type_verdict` is the only place an annotation is read. Its `_Position` carries what
the walk resolved beside the verdict, and `_resolved_position_types` reads that field. It read
only bare names of its own, so the two readers disagreed the moment [AD-67](ad-67-an-undecidable-boundary-position-is-unknown-not-silence.md)
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
| Teach reachability its own collection walk, matching the rule's | Agreement by copy, which is what had just failed: the first revision of this decision did exactly that, and review rejected it. Two call sites stay equal only until the next shape is taught to one. |
| Enter unions and mappings here too | AD-67 left both undecidable for the rule; the two readers must agree, so this follows it rather than overtaking it. |

## Limit

Both readers now enter one level. A nested subscript, a union, a mapping, a dotted name and a
forward reference stay unresolved on both sides, which is the point: they are unresolved
*together*. Reachability now needs the contract passed to it, although resolution does not
depend on it -- the price of reading the verdict's walk rather than repeating it.
`ANALYZER_VERSION` rises to 0.30.0, because a facade function's `facade_types` record gains the
elements it always exposed; merging the two readers adds nothing further, and the output is
byte-identical on a fixed sample.

## Check

`tests/test_analyzer.py::test_facade_types_resolve_a_collection_element` fails on the unmerged
readings. Two structural tests hold the merge itself: exactly one function may call
`_resolve_named_type`, and reachability may not walk collection parameters of its own.
`test_boundary_types_and_facade_types_agree_across_annotation_shapes` compares the two readings
over nine shapes, silence included, and fails when either side alone is taught a new one.
