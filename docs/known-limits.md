# Known limits

Archkeel observes one static snapshot, not runtime behavior, data flow, performance
or responsibility fulfillment. A rationale proves recorded intent, not truth.
Determinism is measured for a machine/runtime, not across every platform.

## Before claiming PASS

A rule needs applicable subjects, complete relevant coverage and sufficient evidence.
`interface_boundary` and `complete_requires` also need unique ownership; missing
receipts keep their rows and aggregate verdict UNKNOWN. Only Python initializers
with no AST statements may be unowned without breaking this proof; docstrings and
imports are statements. An empty violation list is insufficient.

Python `call_owner` supports stable plain top-level functions, plain parameter
annotations, one typed parameter copied to a stable `self` field, proven default
construction, and uniquely inherited method origins for an otherwise admitted
receiver. Inheriting a default constructor alone remains UNKNOWN. Its native witnesses are
limited to import-bound `random.random`, `random.Random` methods,
`datetime.datetime.now`, and `secrets.token_hex`. Other external targets,
constructors, dynamic attributes, custom allocation, descriptors, ambiguous
inheritance, decorated functions/methods, and mutated or revoked bindings remain
UNKNOWN. Dynamic `setattr` or `delattr` with an unresolved member name revokes
native identities under the affected provider. It proves the declared static
boundary, not runtime conformance. See
[AD-252](architecture/decisions/ad-252-bounded-call-identity.md).
This rule requires a source/contract/inventory/call-bound receipt for its exact
claim and observation version; legacy saved observations cannot certify it.
Re-observe pre-release artifacts with inventory-only proofs. These consistency
bindings do not authenticate artifacts. Other language profiles do not support it.

`bounded_numeric_operand` is Python syntax evidence for `%` and `%=` only. It
selects written Name/Attribute terminal identifiers and proves bounded exact
integer/Boolean literals, unary signs, powers and unique preceding aliases.
Known operations and aliases require replayable single-line source excerpts of
at most 16,384 characters; `if`, `elif`, `while`, `for`, `with`, function and
class headers are supported. Multiline or
otherwise incomplete evidence remains UNKNOWN.
Unsupported expressions, unstable or shadowed bindings, oversized values, and
empty or missing selected scopes remain UNKNOWN. It does not infer runtime types,
operator overloads, execution reachability, entropy or collision freedom. See
[AD-246](architecture/decisions/ad-246-bounded-numeric-operand.md).

An explicitly certified `complete_requires` scope can PASS with unrelated source
resolution gaps. Arbitrary imports still block their own scopes and ancestors;
signature gaps do not prove or disprove imports. Legacy or unbound gaps remain
blocking. Global coverage FAIL and exit 2 stay visible
([AD-227](architecture/decisions/ad-227-scoped-dependency-proof.md)).

Named TypeScript constructor parameter properties are observed as direct attributes.
Ordinary parameters and runtime assignments do not declare that inventory. Computed,
malformed and ambiguous members still prevent completeness
([AD-230](architecture/decisions/ad-230-typescript-parameter-properties.md)).

Complete native Dart/TypeScript direct-member inventories can retain certified
local proof despite an unrelated resolution gap. Local gaps, unsupported members,
ambiguous owners and missing native proof still prevent complete inventories.
This does not certify inherited/runtime members, signatures, whole-Target UML or
global coverage ([AD-229](architecture/decisions/ad-229-local-member-inventory-proof.md)).

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

## Python declaration and runtime proof

Source declaration identity is separate from runtime member and creation proof.
An opaque alias transfer can retain the known declaration and its source violations
while blocking an exact allowance. Missing or mutated binding identity remains
UNKNOWN. Exact metadata allowances also need positive member-binding evidence;
a class header alone cannot rule out metaclass replacement.

Creation and alias-value proofs cover bounded builtin forms and supported native
providers. Arbitrary operators, class namespace redirects and opaque module/object
transfers can invalidate proof across the scanned closure. Captured provider source
does not establish runtime immutability or arbitrary factory behavior.

## Other static blind spots

- Calls are partly resolved. Annotated receivers do not enforce runtime types;
  candidates are not confirmed calls. Unresolved calls feed regression measures.
- Python literal loaders contribute bounded dependency evidence; unproved bindings,
  targets and nonempty builtin fromlists withhold affected dependency receipts. See
  [supported loader forms](architecture/python-dynamic-dependencies.md). As-written
  construct matching can miss aliases or report shadowed names. Type-checking
  imports still count in cycle graphs.
- Facade name budgets need provable exports and uses. Dynamic `__all__` mutation,
  bare module imports and unenumerated stars cannot prove counts.
- Package roll-up cycles need not be module cycles. Read their backing SCC evidence.
- Physical folders, filters and renderer routes prove no ownership or conformance.
  Dense layouts may warn; the verdict does not change.

## TypeScript profile

Import graphs, ownership, externals, cycles and layout are measured. Lexical UML
declarations, members, signatures and proven local relationships are available;
they do not provide compiler type checking or Python-style symbol/type rules.
Type and value definitions with the same name can match distinct UML intent;
same-namespace duplicates, class/enum overlaps and declaration merging remain UNKNOWN
([AD-233](architecture/decisions/ad-233-typescript-namespace-identities.md)).
Written string comparisons and switch cases provide PARTIAL construct evidence:
observed prohibited forms can FAIL, but an empty inventory remains UNKNOWN.
Other construct forms, call and private-use metrics remain unavailable. See
[supported string controls](architecture/typescript-written-string-controls.md).
Computed/indirect
loaders, incomplete JavaScript closure and missing resolver inputs retain UNKNOWN, as do
`extends` through a package, `exports` and `typesVersions` maps, and syntax the
grammar cannot parse (`import('x').T<G>`, `export type *`).
See [adapter limits](architecture/typescript-foundation-proposal.md#evidence-and-limits).

## Dart profile

The Python-hosted Dart collector records declarations, classifier members, syntax signatures,
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
