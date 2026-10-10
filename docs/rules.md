# Architecture rules

Choose policy from observable evidence. [The contract schema](../schema/architecture-contract.schema.json)
owns fields and versions; [valid examples](../tests/contracts/valid/) show accepted
syntax. [Known limits](known-limits.md) define what a scan cannot prove.

## Class A: deterministic rules

PASS requires applicable subjects, complete relevant coverage and sufficient evidence.
`interface_boundary` and `complete_requires` also need unique ownership.
Known violations remain FAIL beside UNKNOWNs. No finding alone proves conformance.
Unsupported capabilities cannot PASS.

| Need | Rule |
| --- | --- |
| Every module has one owner | `complete_assignment` |
| Exact immediate package/module layout | `root_layout` |
| Approved outbound component dependencies only | `complete_requires` |
| Reject a component, module or symbol crossing | `forbidden_dependency` |
| Record permitted component direction | `allowed_dependency` — permission, not PASS |
| Only declared public interfaces are imported | `interface_boundary` |
| Independent peers never import each other | `sibling_isolation` |
| Confine an external package to selected sources | `external_dependency_scope` |
| Reject undeclared non-stdlib dependencies | `complete_external_scope` |
| Reject component or module import cycles | `no_component_cycles` |
| Put classes of selected kinds in chosen modules | `symbol_placement` |
| Reject broad containers or unpublished owned facade types | `boundary_types` |
| Forbid selected syntactic constructs | `forbidden_construct` |
| Declared requirements follow layer direction | `layer_order` |

### Ownership and dependency decisions

`packages` owns descendants; `exact_modules` owns only named modules. Competing
owners have no precedence. `namespace` adds physical placement policy without
changing semantic ownership. Choose a type's owner before applying placement rules.

With `complete_requires`, each source component's `requires` lists its permitted
outbound pairs; missing or empty lists forbid them. Optional `through` restricts
the required component's module prefixes. Targets must exist in the same contract.
Without this rule, pairs remain explicitly allowed/forbidden decisions; missing
pairs are open. Narrow symbol/submodule rules do not decide a whole pair.
`allowed_dependency` records permission even without an observed import.

`forbidden_dependency.allowed_sources` is exact. Other scoped allowances use
prefix `allowed_sources` and exact `exact_sources`. Type-checking filters affect
rule evaluation, not cycle graph collection. Component and module cycles differ;
choose both rules if both matter. Known SCC contractions can shrink baselines.

### Interfaces and types

`public` governs component crossings; `module:Name` publishes one name, while a
module entry uses its export surface. A cross-component import or proven facade
signature can establish use. Unbuilt interfaces belong in `planned`; built but
unreached entries remain target work. Reached entries need promotion to public.
Publication does not establish cohesion or runtime access control.

`boundary_types` inspects declared facade signatures and supported model fields,
not every helper. Types published by their actual owner, builtins, enums and
Pydantic models qualify. Broad maps and native `object` need reviewed exact
allowances. `allowed_positions` removes only its matching finding; other member
findings and UNKNOWNs remain. Accepted opacity never proves type closure.
For a DTO's native map value, combine `field_path` with `container_depth` and
the complete field `annotation`. Only one alias-free map and literal `object`
or `list[object]` value can match. Depth counts containers from the signature,
including containers before the DTO; fields and unions do not add depth.
The outer map needs a separate allowance. An inline union can also select alternative
maps with proven string keys: string-valued arms plus exactly one `object` or
`list[object]` arm. The complete root or field annotation permits those outer
maps; a separate depth selector permits only the native value. Nested simultaneous
maps, aliases, unknown arms and repeated native values grant nothing through this
union rule. See [AD-216](architecture/decisions/ad-216-native-mapping-alternatives.md)
and its tests. Ambiguous paths or occurrences grant nothing.
For one direct `Mapping[str, list[dict[str, object]]]` signature, use the complete
annotation with three separate allowances: no depth for the outer map,
`mapping_depth: 2` for the inner map, and both `mapping_depth: 2` and
`container_depth: 3` for its `object` value. This requires a proven, alias-free
map → list → map → object chain; tuple wrappers, DTO fields and union arms do
not qualify. See [AD-217](architecture/decisions/ad-217-nested-map-allowances.md).
For a direct `Iterable[object]` or `Iterable[object] | None` signature, an exact
callable, position, complete annotation, empty `field_path` and
`container_depth: 1` permit one native element. Standard `typing` or
`collections.abc` origin and builtin `object` must be proven. Aliases, DTO fields,
wrappers, other collections and additional union arms do not qualify. The fact
retains accepted opacity; iteration structure does not establish type closure.
See [AD-218](architecture/decisions/ad-218-native-iterable-elements-use-proven-signatures.md).
See [boundary examples](../tests/test_boundary_types_facades.py) before choosing
selectors. Aliases, inheritance, re-exports and unsupported forms require proof.

`forbidden_construct` is syntactic, not a type checker. Use the schema's construct
vocabulary and source scope. Aliases/shadowing are limits. Exact type-ignore
allowances bind scope, line, AST statement and tag; moving or changing them needs
review.

### Nested and independent intent

Explicit `inside` mounts evaluate child contracts over the same scan. Paths are
relative to `--root`; labels and rules are local and mount-qualified. No directory
implicitly creates a boundary. Child public interfaces govern siblings; the
parent's outward API is independent and ancestor restrictions still apply.
Unsupported declarations or invalid mounts fail closed.

Contract 2.2 adds independent `declarations.uml`; see [UML conformance](architecture/uml-model-target.md).
Contract 2.3 adds component `layer` and `layer_order`: ordered inner-to-outer layers
forbid earlier-to-later declared requirements. Missing affected layers remain
UNKNOWN. Older contracts retain their bytes and reject unsupported new fields.

## Class B: regression checks

Revision checks compare counts, exact ratios and semantic fingerprints under
comparable inputs. Stable counts can hide replacements; fingerprints cover
supported changes, not design quality. Existing UNKNOWN remains UNKNOWN even if
nothing regresses. See [reference](reference.md#regression-checks) for the protocol.

`measurement_budgets` select available scalars for baseline validation. Rises fail;
falls require baseline cleanup. Facade/coupling budgets constrain names, so swaps
cannot hide behind stable counts. Over-target accepted names are debt; unavailable
name enumeration cannot PASS. Missing measurements exit 2.

Use the [target-first loop](target-first.md) to preserve intent, baseline debt and
gate widening. New permissions, removed restrictions and unclassified changes
need an amendment bound to the exact contract/baseline pair. Baselines do not
hide diagnostics or UNKNOWN evidence.

## Class C: declarations

Declarations record context and independently authored intent. Their presence,
references and provenance can be checked; truth and responsibility fulfillment
cannot. `public_api` promises external consumers names and exposed types, without
an unused-consumer check. [The API reference](reference.md#reading-a-reports-violations)
names the supported external surface.

`declarations.compat` records permanent or migration shims. A shim has only imports
and literal exports resolving to its target; product imports must avoid it.
Migration shims remain visible work.

## Class D: review claims

Unreferenced symbols, unread bindings, repeated logic, oversized components and
type fan-in are review candidates, never verdicts or scores. Missing signals mean
UNKNOWN, not zero. Outside consumers and runtime dispatch can invalidate a
candidate. Inspect evidence before deleting code or adding boundaries.

<a id="migrating-from-1-1-0"></a>

## Migrating from 1.1.0

Keep top-level components/rules. Move class-C fields under `declarations`, retaining
names and provenance. Set `schema_version` to `2.1.0`; omit unused arrays. Add
requirements and `complete_requires` only after deciding dependency intent.
Run `archkeel validate --root . --json` and review the diff.

Old root-only amendments for mounted contract trees need regeneration and review.
V2 amendments bind canonical before/after baseline policy; legacy v1 supports
contract-only comparisons. Missing baseline and empty baseline differ. Explicit
stale records fail even without widening. Attribution text does not authenticate
approval.
