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
A `/// <reference types="./x" />` directive with a relative or absolute path names a file of the
project; it is UNKNOWN, as `path` and `lib` directives are (#976). A `types` name without a path
stays silent. A `declare module "x"` augmentation names a module as an import does: a relative or
absolute name is UNKNOWN. A bare name is UNKNOWN when the project sets `paths` or `baseUrl` and
the file is a module file (it has `import` or `export`), because those options can map the name
to a project file; the resolver is not asked, so a name that maps to no project file is UNKNOWN
too. Without `paths` and `baseUrl` a bare name stays silent. In a script file `declare module`
declares an ambient module, so it is no concern. A wildcard name (`declare module "x*"`) is a
pattern for tsc (TS2664 in a module file), not a module, so it stays silent.
A `/// <amd-dependency path="x" />` directive is UNKNOWN, as a `path` directive is (#988). When
`typeRoots` holds an entry without `node_modules` in it (a root that may lie inside the project), a
`/// <reference types="name" />` directive is UNKNOWN too, because the name may be a directory of
the project ([AD-354](architecture/decisions/ad-354-a-type-root-inside-the-project-makes-a-types-directive-a-concern.md)).
`self` and `frames` are roots of the global object, like `window` and `globalThis`. A use through
`top` or `parent` is read as a use through the window too, so it is an edge or a gap, never silent;
inside a frame they name another window, so the edge can go to a global of the page above. A write
through them (`top.x = 1`) publishes nothing. A chain of these names (`window.self.x`, `top.window.x`,
`parent.top.x`) is read like one of them (#1007).
The native TypeScript collector reads a file up to 4 MiB. Above that size it gives UNKNOWN for
the file, where the Python collector reads the file and can give FAIL. The two collectors give
the same facts only for files under the limit.

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
into another crate of the workspace names its deepest module. The collector also reads the
definitions of each module (symbols, AD-351). `interface_boundary`, calls, types and constructs
are unsupported, so they stay UNKNOWN and never PASS. A name that a
file declares more than once and that may name a module, a glob that the scan cannot follow, a
`use` path that starts with a name that a glob may bring in, a `super` above the crate root, two
`macro_rules!` of one name and a path in a `macro_rules!` body that is relative to the place of the
call are UNKNOWN, and so is a macro call that the scan cannot place (in the tokens of another macro, or by the path of a module). A `crate::` path in a macro body is an edge of each call (AD-349). Edition 2015 (or none named
in the manifest): a `use` path and a `::` path start at the crate root. A method of an `impl` block
in another module than its type is an edge when a path names it (`impl crate::c::S { fn m() }` in
`b` and `crate::c::S::m()` in `a`: `a -> b`). A method call `x.m(..)` that may reach such a method
(it has `self`, the same number of other arguments, and a visibility that holds the caller), and a
call of a method of a trait that a glob brings in (`use b::T;` in the parent, `use super::*;` and
`5u8.m()` in the child), give a gap of the pair `a -> b`. A call on a plain `self` in a method of `impl S`, or a path `Self::m`, is an edge to the module of the one inherent member `m` of `S` and gives no gap when that member has the same `self` form (`self`, `&self`, `&mut self`) and no `cfg` or other attribute can change the member, its block, its module, the type or the caller; any other case keeps the gaps (AD-383). The host drops that gap only when the
contract lets `a` use `b` and the edge closes no cycle that the edges and the other pair gaps may
close (AD-357). Open false PASS, not accepted (#1004): a trait `impl` in another module than its
trait and its type, and a trait of a crate outside the workspace that a glob brings in. Open false
PASS, not accepted (#1020): an item that a macro generates. Not seen, and the verdict can be PASS:
a path into another crate that goes through a `pub use` of its root. A rule on a module pair
forbids a direct use; a use through a re-export is seen by the layer and cycle rules (AD-357). For
`pub use crate::b::make;` in `c` and `use crate::c::make;` in `a`, the edge of `a` goes to `c` and
the edge of `c` to `b` (a `reexport` record); a module cycle through such a `pub use` gives FAIL
(`tests/test_collector_false_pass_rust_impls.py`). The same holds for `pub use crate::b::*;` in `c`
and `use crate::c::*;` in `a`. A macro call with a path in its body, an exported `macro_rules!`, `include!`, a `cfg` that gates a `mod` or
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

### Rust: what the collector does not prove

- **Definitions** ([AD-351](architecture/decisions/ad-351-the-rust-collector-reports-definitions-and-never-invents-one.md)).
  An item that a macro call generates is not listed, and nothing is invented for it. A method of an
  `impl` block is listed only when its type is a definition of the same module, so `impl Builder`
  in another module than `Builder`, an `impl` of a foreign type and an `impl` of a type that a macro
  generates give no method. A gap would make the whole scan incomplete, so the report says
  `partial` for the symbols of each module and for the methods of each type. A field, an
  associated type and the visibility of a `mod` are not read. A definition under a `cfg` that the
  scan does not know is read (the union of the cases). `interface_boundary` stays unsupported until
  the uses of an item are resolved (slice 5b-4b).
- **`extern crate` without a manifest entry.** `extern crate base_crate;` with no entry in
  `Cargo.toml` is UNKNOWN, never PASS. It compiles only when a `build.rs` prints
  `cargo:rustc-link-search=crate=...`. Such a link is not read
  ([AD-356](architecture/decisions/ad-356-a-call-or-crate-that-a-producer-cannot-see-is-a-gap.md)).
- **An attribute name in a macro body** is read as a derive helper, not as a crate name
  ([AD-335](architecture/decisions/ad-335-archkeel-checks-the-rust-of-native-with-its-own-contract.md),
  amendment (b)). A crate that a macro reaches through such a name is seen only when the manifest
  declares it.
- **`macro_use` and `cfg(any(test, feature = ...))`** are read (amendment (c)). A `macro_use` on a
  module takes the macros of that module as code of the crate. A `cfg(any(...))` with only known
  conditions is read as active or inactive; a feature set that the manifest does not list is not
  checked.
- **The reader handles only part of TOML.** It reads tables, arrays of tables, dotted keys, inline
  tables, arrays and strings. A basic string decodes the escapes of TOML (`\uXXXX`, `\UXXXXXXXX`)
  and a multi-line string decodes as TOML does. A number, a date or a boolean is not read, because
  no key that the collector needs holds one. The reader refuses an escape that TOML does not
  define, a surrogate in an escape, a key that is set twice, text after a value and nesting deeper
  than 64. A refused manifest makes its crate UNKNOWN; the reader never guesses.
- **A file that two owners load.** A file that two modules or two crates load, and a `#[path]` that
  leaves the directory of its crate, make the owners UNKNOWN. The collector does not choose an
  owner for such a file.

## The Rust contract parser

The Rust contract parser (`native/contract`, [AD-359](architecture/decisions/ad-359-the-rust-core-after-the-collector-crates-and-boundaries.md), [AD-364](architecture/decisions/ad-364-the-rust-contract-parser-reads-the-whole-grammar.md)) decides each contract as the Python parser does, with these stricter cases:

- A repeated JSON key is an error (`DuplicateKey`). Python keeps the last value.
- A lone surrogate escape is invalid JSON. Python parses it, and then `contract_bytes` fails with `UnicodeEncodeError`.
- An integer above 2^64 is read as a float, so a field that needs an integer refuses it. Python accepts it.
- The XID tables of `unicode-ident` and of the Python release can differ for a new Unicode character.

A contract that mounts inside contracts parses as `NeedsTree`, not as a complete contract. Only the tree assembly (`policy::assemble_tree`, [AD-366](architecture/decisions/ad-366-the-inside-contract-tree-is-assembled-and-checked-in-the-contract-crate.md)) makes it complete. The dual-run core calls it with the files that the harness reads ([AD-379](architecture/decisions/ad-379-the-core-asks-the-shell-for-the-inside-contracts-and-decides-the-root-rules-of-a-tree.md)); the Python host still assembles the tree. The tree is stricter than Python in these cases:

- Bytes that no mount reads are an error (`Unmounted`). Python reads only what a mount names.
- Two inputs with one repository path are an error (`Duplicate`).
- An input path or identity that is not a repository path is an error (`Unsafe`), for example a symbolic link out of the repository.
- A JSON object with one key two times is an error (AD-364).
- A mount deeper than 900 levels is an issue (`TooDeep`). Python stops near depth 984 with a `RecursionError` and gives no verdict.
- An inside whose resolved path (the identity that the shell sends) differs from its reference is an issue (`Linked`). Python refuses a link to a mounted file as a duplicate mount and accepts a link to an unmounted file inside the repository.
- The core uses no tree with an issue: it names the refusal. Python evaluates the root and the valid mounts. After Cut A, a tree with a missing or cyclic mount gets no root verdict: the run names the refused tree and exits 3. Today Python gives the root verdicts and UNKNOWN for the broken mount.
- The core reads at most 1 024 inside contracts and 64 MiB of inside bytes in one request.
- The core decides the rules of each contract of a tree ([AD-385](architecture/decisions/ad-385-the-core-decides-the-rules-of-a-contract-tree-with-one-model-per-mount.md)). It names an inside `layer_order` rule (its row cites the inside contract file) and an inside `complete_requires` that needs the scan roots, where Python can decide them. A root rule whose id is the scoped id of a mount rule (`domain:SAME` beside the rule `SAME` of the mount `domain`) refuses the tree by name; Python merges the two rules into one.

The crate also compares two trees as `validate --against` does (`policy::compare_trees`, [AD-373](architecture/decisions/ad-373-the-contract-crate-compares-two-contract-trees-for-against.md)). No command calls it yet. It does not recognise a rename (AD-105), so a moved package shows as widenings. Its messages equal those of Python 3.11; on Python 3.12 or later a code point assigned after Unicode 14 gives other message bytes in the Python engine (L-28). No decision depends on a message.

The crate reads, writes and binds an amendment (`policy::parse_amendment`, `policy::bind`, [AD-375](architecture/decisions/ad-375-the-contract-crate-reads-amendments-and-binds-them-to-a-comparison.md)). No command calls it yet. It binds only a run without `--baseline`; baseline application and widenings are not connected yet. The shell must state the baseline fact; for a run with `--baseline` (`Baselines::configured_unsupported()`) `bind` gives `BindError::BaselineNotSupported` and no verdict. It does not recognise a rename (AD-105), so Rust reports widenings where Python sees a rename. It is stricter than Python in these cases:

- Schema 1.0.0 is an error (`Version1`). Python reads it and accepts it for a run without `--baseline`. Write the amendment again with `archkeel validate --against <ref> --amendment <path> --write-amendment --decided-by <who> --rationale <why>` (lead decision L-34b).
- A JSON object with one key two times is an error. Python keeps the last value.
- A lone surrogate escape is invalid JSON. Python reads it and then cannot write it.
- `Binding::amend` refuses a blank `decided_by` or `rationale`. Python writes a file that its reader refuses.
- Nesting deeper than 128 levels is invalid JSON. Python stops with `RecursionError`.

The baseline codec reads schemas 1.0.0 through 1.3.0 and writes 1.3.0 ([AD-386](architecture/decisions/ad-386-the-contract-crate-reads-and-writes-baselines.md)). It keeps every entry and the permissive Python string rules. It refuses repeated JSON keys, lone surrogates, numbers outside its integer range, nesting deeper than 128 and files over 16 MiB. No command uses it yet.

The API list of `tools/rust_api.py` reads a declaration macro once, in its template. The
contract types that `record!`, `text_type!`, `closed_enum!` and `rules!` build are not in the
lists of `native/api_baseline.json`. Two `pub fn` of the same name in two `impl` blocks of one
file are two equal lines, so a move between the two blocks does not show (AD-382).

The system-access test of the core side (AD-382) is a text scan. It does not see an access
through another crate, a method on a value of a type that it does not name (except the file
methods of `Path` by name), a macro such as `eprintln!` or `include_str!`, or an io trait method.

## The Rust core (dual run only)

The Rust core (`archkeel-core`, [AD-378](architecture/decisions/ad-378-a-rule-passes-only-with-the-scope-proof-of-its-own-model.md)) runs only in the dual run; no command uses it. Its scope proof is stricter than Python in these cases, each a named gap, never a PASS:

- A gap between two modules that the contract allows: Python drops it for the Rust profile only. The core names each rule and the run for it. For another profile both engines keep the gap ([AD-384](architecture/decisions/ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md)).
- `interface_boundary` in a TypeScript contract: a limit of the Rust profile only. 8 rules (PASS in Python).
- A symbol-level selector in a reply with `script-globals-v1`: one profile reads such selectors. 4 rules (PASS in Python).
- A runtime requirement that is not `>=X`, and a `forbidden_construct` rule that selects no module: no corpus case.
- `complete_requires` ([AD-380](architecture/decisions/ad-380-the-core-decides-the-direction-rule-kinds.md)): a coverage gap that the dependency scope proof of the host can accept is a named gap for this kind. The receipt reads the scan roots of the request ([AD-384](architecture/decisions/ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md)); a contract with a selector rule (its source is a receipt scope) is a named gap.
- The cycle receipts and the receipt of `complete_requires` map a module file to its directory only for a profile with a proven import closure (`Layout::ProjectFiles`); any other profile is a named gap.
- A `layer_order` rule without the source of the contract bytes in the request: a named gap. The core does not read the contract file again after the shell read it.
- A `requires` symbol port in a reply without the symbol feature: the import is left out, as in the store-accepted profiles.
- The contract path in the dual-run request is the word of the caller. It sets only the evidence id of the `layer_order` rows, never a verdict: the model binds the bytes to the parsed contract by their digest, not the path.

The core decides one rule kind set where Python does not ([AD-384](architecture/decisions/ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md), "core decides, Python does not"). Python makes every rule UNKNOWN for a pair gap that it keeps. The core holds only the rules whose reading the gap can change, and it passes the others. The run stays UNKNOWN and names each kept gap. The frame lists each such rule in `beyond`, and the harness shows it as a named difference. The corpus has 21 such rules in 16 cases (`BEYOND_CASES` in `tests/test_native_core.py`). Two limits apply:

- The Rust collector does not mark an external `pub use` as a re-export. So a gap into a module with any external import holds `external_dependency_scope` and `complete_external_scope`.
- The gap scope reads the edge model of the collector, as Python does. A glob that brings in a trait through a `pub use` chain `b -> d` gives the gap `a -> b`, not `a -> d`, so a rule on `a -> d` passes (review N2 of #1084). With the explicit call both engines record only `a -> b`.

The dual-run request is a test protocol. Its `collector_argv`, `pinned` and `standard_library` fields are the word of the caller, not evidence: a wrong producer or an extra standard library name can give a PASS that Python does not give. The request of M1 must not take them from a caller: the shell starts the pinned collector, checks its digest and fills the producer and the standard library from its own profile table.

## The native Python collector

The native Python collector (not yet the default) cannot read the target of a dangling `*.py`
link. When the scan leaves tests out, each dangling link is a named gap and the scope is not
complete, also where Python would judge the target as production code (AD-367 point 5).

Its definition table (AD-377, not in the reply yet) gives a module a named gap and no symbol
record for: an expression deeper than 100 levels (Python writes its text up to its
RecursionError at about 158 levels), a lone surrogate escape in a string, a 3.12 format spec
with `\N{...}` or a backslash in a raw spec, and a spec deeper than two levels.

The native Python collector also refuses compiler-invalid ASTs and sources beyond its validation
work or depth bounds. Each refusal names the file and gives incomplete scope
([AD-389](architecture/decisions/ad-389-the-native-python-collector-checks-compiler-refusals-before-facts.md)).
**Python reply acceptance — entry condition:** the store must not accept the native Python reply
before #1072 is closed. The refusal checks are partial: 17 known classes still accepted, issue #1072 stays open.

## Scope and nested contracts

A run covers only configured roots and namespace. Adjacent tests need another
configuration, contract and output path. Their product imports are external, so
product-module boundaries cannot be expressed from that namespace.

Only explicit `inside` mounts evaluate child contracts. Invalid mounts prevent
complete observations and baseline/graph writes. Child public interfaces govern
siblings, not the parent's outward API. Unmapped scope prevents proof. Use
[reference](reference.md) for path and gate semantics.
