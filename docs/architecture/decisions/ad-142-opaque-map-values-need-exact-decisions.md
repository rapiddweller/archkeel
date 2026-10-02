# AD-142 Opaque map values need exact decisions

## Problem

An allowed `dict[str, object]` still exposes an unnamed opaque value. Neither the
outer-map decision nor a DTO field path names that occurrence (#253).

## Decision

Add optional positive-integer `container_depth` to the existing exact allowance.
Its full signature annotation, callable and parameter/return remain mandatory.
An empty field path and depth1 select the value of a top-level map. Collections
and mappings increase depth; unions do not. The outer map needs a separate entry.

Reuse the resolver's mapping occurrence, value annotation and alias-route facts.
Match only a literal `object` value of one pathless, alias-free mapping, and exactly
one matching opaque occurrence before finding deduplication. Never pick the first.
Emit accepted-opacity FACT evidence with decision provenance; closure is unproven.

| Input | Result |
|---|---|
| Separate exact outer and value decisions | Both findings accepted; opacity remains explicit |
| Outer map only | Value still violates |
| Value only | Outer map still violates |
| Other symbol, return, annotation or depth | Unmatched |
| Object key, duplicate siblings/maps, value alias | Unmatched |
| Unresolved member or neighbor | UNKNOWN remains |

## Rejected

Implicitly extending outer permission would hide undeclared contents. A generic
type-argument path, wrapper model or alternate resolver is unnecessary here.

## Compatibility and limit

Omitted depth preserves canonical bytes, digests and existing allowance behavior.
Adding or changing depth is an ordinary contract widening requiring amendment.
This selector cannot declare type closure or select ambiguous/named DTO routes.
Root native payload and nullable-constructor controls keep AD-135 behavior.

## Checks

`tests/test_boundary_type_opaque_map_values.py`; `tests/test_contract_model.py`;
`fixtures/demo_catalog_types.py` positive, missing-value and UNKNOWN CLI demos.
