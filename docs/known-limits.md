# Known limits

Archkeel observes one static snapshot, not runtime behavior, data flow, performance
or responsibility fulfillment. A rationale proves recorded intent, not truth.
Determinism is measured for a machine/runtime, not across every platform.

## Explore without a contract

`archkeel explore` detects one top-level Python package only. TypeScript and Dart need
`--language`, `--source` and `--namespace` (and `--tsconfig`). Its components follow the
package layout; they are not decisions. Entry modules are `__main__` modules only. An import
edge is not a call edge or a runtime order. A contract with components but no rule gives
`target: unavailable` and no rule verdict
([AD-285](architecture/decisions/ad-285-explore-without-a-contract.md)).

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

Named numeric operands inside Python 3.12 generic function and class definition
intervals, including defaults, remain UNKNOWN because their header scopes are not
replayed independently. Literal operands remain provable; decorators stay in their
outer scope.

`forbidden_call_argument` requires a unique, statically proven target
declaration and observed callable signature. Only explicit actuals with
complete, valid bindings are considered; spreads, duplicates, missing
signatures and unproven calls leave the scope UNKNOWN. Omitted defaults are not
actuals. Calls without canonical binding carry `call_arguments: null`; a
canonical call whose complete actual inventory cannot be tied to a bounded
source excerpt also keeps its binding but carries null arguments and remains
UNKNOWN for argument rules. Both cases differ from a proven call with an empty
argument list. The first slice
recognizes written string constants, including empty and adjacent literals;
f-strings, concatenations and named expressions remain unclaimed. It does not
check actual type compatibility. Argument facts require
observation 2.5 and contract 3.10; older readers reject the new evidence.
`forbidden_effect_under_condition` proves only declared Boolean parameters or members,
truth/negation, `if`/`else`, ternary expressions, and early `return`/`raise` domination.
It follows at most one unique private helper whose actuals bind to its observed signature.
Reassignment, named expressions, short-circuit Boolean operators, loops, exception/finally
paths, reflection, ambiguous identities, helper chains and recursion remain UNKNOWN. A
known forbidden effect remains FAIL beside unrelated UNKNOWN paths. These receipts bind
the source, contract, selected inventory, effect and exact rule claim; they are consistency
bindings, not artifact authentication ([AD-250](architecture/decisions/ad-250-bounded-guarded-effect-ownership.md)).

`catalog_argument` and `catalog_use` currently consume unique scanned Python enum declarations with literal string member values and the existing call/reference facts. `catalog_use` can count a string actual only when its optional target and parameter identify a proven read operation; unrelated same-text calls do not count. Non-literal enum values, dynamic projections, non-Python catalogs and ambiguous or incomplete source scopes remain UNKNOWN. Overlay selectors identify enum declaration owners. This is syntactic source use, not runtime reachability. The argument member-reference case depends on #613 call identity and #617 canonical read roles in the final stack.
`forbidden_construct.selector` adds nominal Python selections for member reads,
reflection probes, constructors, type probes, equality, membership, `match`,
`startswith` and `endswith`. The current receiver proof begins with direct unique
annotations on scanned classes. Dynamic reflection names, unannotated or
ambiguous receivers and scopes with no selected subject remain UNKNOWN. Other
language profiles do not support this slice. Selector facts require observation
2.6 and contract 3.11; older readers reject the new evidence.

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

The bundled collector has a 300-second deadline unless `[scan] collector_timeout_seconds`
raises it. Timeout exits 2 without a complete observation. An older report file is not
fresh evidence. Match the analyzed project's Python runtime to avoid `runtime_mismatch`.

## A facade type position is not always decidable

Supported annotation and re-export forms are defined by
[boundary tests](../tests/test_boundary_types_facades.py) and [rules](rules.md).
Unproved routes, missing annotations, ambiguous bindings and unsupported shapes
remain UNKNOWN. An uncertain export cannot hide another private-type violation.
A name that a class-body statement binds at any place makes its class annotations UNKNOWN on
every Python version, because 3.14 evaluates them lazily (PEP 649). A `locals()`, `vars()`,
`globals()`, `exec` or `eval` in the class body makes every class annotation UNKNOWN.
A field `date: date` is one false UNKNOWN. ArchKeel does not see these writes outside the class
body ([#775](https://github.com/rapiddweller/archkeel/issues/775)):
- On 3.14: `__slots__`, `setattr`, a class decorator, a write from another module, a module-level
  `globals()['object'] = Hidden`, and `global object; object = Hidden` in a method.
- On every version: a metaclass `__prepare__` that puts the name in the class namespace.

See [AD-283](architecture/decisions/ad-283-a-later-class-binding-blocks-every-annotation.md).

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

The 3.13+ standard library layouts (a module `__getattr__`, a star import, a
`sys.modules` child publication) are proven only for top-level standard library
modules, and a publication only when every import of the initializer is a
top-level standard library module. A package of several star imports (`pathlib`
on 3.13) binds a name only when the last star source alone lists it in a literal
`__all__` ([AD-278](architecture/decisions/ad-278-a-stdlib-star-facade-binds-the-names-of-its-sources.md)).
A stdlib module that changes another stdlib module through a stored member call
is not tracked (trusted). Code outside the scan, for example a project that
patches a stdlib module at run time, is not tracked either.

## Source syntax newer than the interpreter

ArchKeel reads Python source with the `ast` module of the interpreter that runs it. Code with newer
syntax (for example `except A, B:` from Python 3.14, PEP 758) is a parse failure on an older
interpreter. A `runtime_mismatch` diagnostic names the running version and the full
`requires-python` range. It blocks a complete scan. Select a Python version that satisfies the
full range, then retry with `uvx --python <compatible-version> archkeel <command>`. ArchKeel does
not install or select that interpreter. The tool supports Python 3.11 and newer. The nightly job
checks 3.12, 3.13 and 3.14 (#724, #743).

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
- `archkeel view check` proves structure, not runtime order: an import or a call is not an
  execution trace, and a step needs one direct edge. A Python snapshot records a
  `dynamic_call_limit`, so a call edge is `unknown`, never `missing`. A call through a
  re-export, such as `shop.store.OrderRepository`, proves no call edge. `from p import sub`
  records only `p.sub`, so an absent import of `p` is `unknown`. Symbols, inside components,
  paths and names outside the scanned roots are not view nodes: they are `unknown`. A claim
  is author text, also when the graph has the same edge. A `TYPE_CHECKING` import stays a
  proven import with the reason "type-only import: not executed at runtime". The saved
  snapshot is not authenticated: the check rejects a record with missing evidence, but a
  forged record with consistent evidence passes (#796). A snapshot from `archkeel explore`
  marks its layout contract without a typed marker yet: its `declared` and `requires`
  statuses are not reliable
  ([AD-284](architecture/decisions/ad-284-studio-shows-views-as-checked-data.md)).

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
`extends` through a package, `exports` and `typesVersions` maps (unless bundler mode
is on, where the package is an external edge), and syntax the grammar cannot parse
(`import('x').T<G>`, `export type *`).
`[scan] bundler = true` opts a bundled project into treating tsconfig `paths` aliases
(not `baseUrl`-only matches), package `exports`/`typesVersions`, and existing asset
and JSON imports as known. It requires `moduleResolution: bundler` and asserts that
the bundler's aliases match tsconfig `paths`; ArchKeel does not verify that. A
`?query` on a source file does not make it an asset. A bare-package asset must lie inside
the installed package (a `.` or `..` segment is unresolved). `.` and `..` imports count as
relative. Triple-slash and JSDoc-import
concerns remain
([AD-260](architecture/decisions/ad-260-typescript-bundler-mode.md)).
A JSDoc-import concern needs a JavaScript file and an `@import` tag or `import()` in the type
of a tag: tsc 5.9.3 ignores JSDoc types in TypeScript files, and prose is no type (#744).
See [adapter limits](architecture/typescript-foundation-proposal.md#evidence-and-limits).
Standard globals follow the pinned TypeScript lib files
([AD-261](architecture/decisions/ad-261-typescript-standard-globals-from-lib-files.md)):
a `lib` value the pinned compiler does not name, `noLib` or `libReplacement` leaves them unproved.
`types` and `typeRoots` add names the catalog does not hold, so those names stay unproved
([AD-274](architecture/decisions/ad-274-types-add-and-project-declarations-publish.md)); a
project `declare` of a name, in a global script or a `declare global` block, proves that name.
Without `lib`, the target's default file applies, DOM included. Only top-level value declarations count, so types such as `Document` are not
proved, and a newer `lib` name waits for the pinned TypeScript version to move.

## Dart profile

The Python-hosted Dart collector records declarations, classifier members, syntax signatures,
and resolved bases, calls, references, constructions and local bindings. It does
not prove runtime dispatch, live object identity, or exhaustive call-site coverage.
Dynamic dispatch, missing resolver inputs, malformed units and unsupported
declarations stay UNKNOWN. Own-package resolution uses the package name from
`pubspec.yaml`; snapshot resolution inputs must be present. Python-only
type/construct rules and unmeasured budgets remain unsupported or UNKNOWN.

## Rust profile

The native Rust collector reads the crate edges: a `use` path or a qualified path whose first
segment names another crate, and the module edges inside a crate: a path that starts at `crate`,
`self`, `super`, a child `mod`, a `use` binding or a glob `use` and names another module. A path
into another crate of the workspace names its deepest module. `interface_boundary`, symbols,
calls, types and constructs are unsupported, so they stay UNKNOWN and never PASS. A name that a
file declares more than once and that may name a module, a glob that the scan cannot follow, a
`use` path that starts with a name that a glob may bring in, a `super` above the crate root, two
`macro_rules!` of one name and a path in a `macro_rules!` body that is relative to the place of the
call are UNKNOWN. A `crate::` path in a macro body is an edge of each call. Not seen: a method that
an `impl` block of another module defines (no path names that module), an item that a macro
generates, a re-export chain (the edge goes to the module that the path names, and the
re-exporting module has its own `reexport` record), and a path into another crate that goes
through a `pub use` of its root. A macro call with a path in its body, an exported `macro_rules!`, `include!`, a `cfg` that gates a `mod` or
`use` (except `cfg(test)` and a declared feature), a `path` attribute that is not a literal, an
attribute macro on a module, brackets nested deeper than 256 and a module deeper than 64 levels
make the scan UNKNOWN, and so does a path whose first segment is a crate name that the file also
declares or imports (`::` makes it the crate). A reachable crate name that appears in a macro body, an attribute stream or a string, with no edge to that crate in the file, is UNKNOWN too. A local variable or a field with that name is not. A dependency that a Cargo.toml declares (normal, dev, build, also the underscore forms and
`[target.*]`) is a crate edge even when no source uses it: a crate cannot use a crate that it does
not declare. A dependency table that the reader does not know is UNKNOWN. A `macro_rules!` that
stays in the crate is read as code of its file, and an exported one is UNKNOWN. A planned crate
has no component in the native contract until it has code. Test code (`cfg(test)`, `tests/`, dev-dependencies) counts as production
code until the host key `[scan] exclude_test_sources` is set. With the flag, a `cfg(test)` or `cfg(all(test, ..))` item, module,
impl or trait member and `let` or macro statement, a `#[test]`, `#[x::test]` or `#[rstest]` function, and the `tests/`, `benches/` and `examples/` targets
leave the reply. A `cfg` on a field, a match arm or an expression stays in scope, and so does a test attribute that this list does not
name (`#[test_case]`). A production target or module file in a test directory is UNKNOWN, because the host refuses a reply that selects it. A platform wheel carries the collector; an install without it
reports `missing_tool`
([AD-335](architecture/decisions/ad-335-archkeel-checks-the-rust-of-native-with-its-own-contract.md)).

## Scope and nested contracts

A run covers only configured roots and namespace. Adjacent tests need another
configuration, contract and output path. Their product imports are external, so
product-module boundaries cannot be expressed from that namespace.

Only explicit `inside` mounts evaluate child contracts. Invalid mounts prevent
complete observations and baseline/graph writes. Child public interfaces govern
siblings, not the parent's outward API. Unmapped scope prevents proof. Use
[reference](reference.md) for path and gate semantics.
