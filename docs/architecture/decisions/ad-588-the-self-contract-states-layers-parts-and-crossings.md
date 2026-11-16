# AD-588: The self-contract states layers, parts and crossings

Status: accepted (owner order). Part of #880. It extends AD-335 and AD-432.

## Context
`native/architecture-contract.json` named one component for each crate and 62 forbidden pairs. It did
not say the order of the crates. A reader had to derive the order from the pairs, and a new crate had
no place until someone wrote its pairs. The order was only in a test (`tests/native_rules_support.py`:
`BASE`, the collectors, `collect`, `CHAIN`).

## Decision
1. The contract moves to schema version 3.14.0. The version gates features only; no statement changes.
2. Each component has a `layer`, and the first rule, `NATIVE-LAYER-ORDER` (`layer_order`), gives the
   order from the inside to the outside:
   `foundation` (facts, build, pytext, dart-grammar), `transport` (snapshot, wire, store),
   `collector` (the parts of the four collectors), `collector-entry` (the four entries),
   `collection` (collect), `contract`, `model`, `barrier` (model-barrier), `evaluation`, `report`,
   `core`. The order is the crate order of the test, not a new one. A declared `requires` that points
   to a higher layer is a FAIL. A component without a layer holds every rule UNKNOWN.

All 62 forbidden rules stay. The order rule reads the declared `requires`. A forbidden rule reads the
import facts by module name, with no declaration and no owner between. The two guards fail for
different mistakes, and a forbidden rule gives its own reason in the result.
- 35 rules forbid a direction that the order forbids too, when `NATIVE-REQUIRES-COMPLETE` passes:
  the upward chain `contract`, `model`, `eval`, `report`, `core`, and each collector and `collect`
  to the decision side.
- 15 rules forbid a direction that the order permits: `core`, `eval`, `model` and `report` to the
  TypeScript and Rust collectors, `eval`, `model` and `report` to `collect`, and each collector to
  `store`.
- 12 `NATIVE-PY-*` rules are between parts of the Python collector in one layer.

The crate order test stays. It permits less than a linear order: `model-barrier` reaches nothing above
`facts`, and `contract` reaches no collector.

## Price
The order has 11 names for 56 components. A new crate needs a `layer`, or the self-check is UNKNOWN.
The self-check has 85 rules (84 before).
