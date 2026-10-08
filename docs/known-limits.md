# Known limits

Archkeel observes one static snapshot, not runtime behavior, data flow, performance
or responsibility fulfillment. A rationale proves recorded intent, not truth.
Determinism is measured for a machine/runtime, not across every platform.

## Before claiming PASS

A rule needs applicable subjects, complete coverage and sufficient evidence.
`interface_boundary` and `complete_requires` also need unique ownership; missing
receipts keep their rows and aggregate verdict UNKNOWN. Only Python initializers
with no AST statements may be unowned without breaking this proof; docstrings and
imports are statements. An empty violation list is insufficient.

The bundled collector has a 300-second deadline. Timeout exits 2 without a complete
observation. An older report file is not fresh evidence. Match the analyzed project's
Python runtime to avoid `runtime_mismatch`.

## A facade type position is not always decidable

Supported annotation and re-export forms are defined by
[boundary tests](../tests/test_boundary_types_facades.py) and [rules](rules.md).
Unproved routes, missing annotations, ambiguous bindings and unsupported shapes
remain UNKNOWN. An uncertain export cannot hide another private-type violation.

Inherited boundary methods follow a uniquely resolved local single-base chain.
Inherited fields and full MRO are unproved. External API closure has a separate
one-base walk with supported generic field substitution. Multiple bases, cycles,
dynamic bodies and unresolved inherited types prevent closure.

Accepted broad maps and native `object` record reviewed opacity, not type closure.
An allowance cannot clear uncertainty elsewhere. Non-exempt UNKNOWN evidence
prevents aggregate PASS; external-type positions outside component policy and
standing scan disclaimers retain their separate meanings.

## Other static blind spots

- Calls are partly resolved. Annotated receivers do not enforce runtime types;
  candidates are not confirmed calls. Unresolved calls feed regression measures.
- Dynamic imports add no static dependency edge. As-written construct matching
  can miss aliases or report shadowed names. Type-checking imports still count
  in cycle graphs.
- Facade name budgets need provable exports and uses. Dynamic `__all__` mutation,
  bare module imports and unenumerated stars cannot prove counts.
- Package roll-up cycles need not be module cycles. Read their backing SCC evidence.
- Physical folders, filters and renderer routes prove no ownership or conformance.
  Dense layouts may warn; the verdict does not change.

## TypeScript profile

Import graphs, ownership, externals, cycles and layout are measured. Lexical UML
declarations, members, signatures and proven local relationships are available;
they do not provide compiler type checking or Python-style symbol/type rules.
Construct, call and private-use metrics remain unavailable. Computed/indirect
loaders, incomplete JavaScript closure and missing resolver inputs retain UNKNOWN, as do
`extends` through a package, `exports` and `typesVersions` maps, and syntax the
grammar cannot parse (`import('x').T<G>`, `export type *`).
See [adapter limits](architecture/typescript-foundation-proposal.md#evidence-and-limits).

## Dart profile

The native Analyzer records declarations, classifier members, syntax signatures,
and resolved bases, calls, references, constructions and local bindings. It does
not prove runtime dispatch, live object identity, or exhaustive call-site coverage.
Dynamic dispatch, missing resolver inputs, malformed units and unsupported
declarations stay UNKNOWN. Own-package resolution uses the package name from
`pubspec.yaml`; snapshot resolution inputs must be present. Python-only
type/construct rules and unmeasured budgets remain unsupported or UNKNOWN.

## Scope and nested contracts

A run covers only configured roots and namespace. Adjacent tests need another
configuration, contract and output path. Their product imports are external, so
product-module boundaries cannot be expressed from that namespace.

Only explicit `inside` mounts evaluate child contracts. Invalid mounts prevent
complete observations and baseline/graph writes. Child public interfaces govern
siblings, not the parent's outward API. Unmapped scope prevents proof. Use
[reference](reference.md) for path and gate semantics.
