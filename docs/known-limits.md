# Known limits

## Supported projects on main

Main supports Rust and TypeScript projects, and the import rules of Python (AD-450) and Dart (AD-468) projects.
A Python project gets PASS or FAIL only for rules that read the import graph. A dynamic import,
an import-system change and the other gaps of AD-450 give UNKNOWN for each rule of the run.
Python rules that read symbols, calls or constructs stay UNKNOWN. A Dart project gets PASS or FAIL
only for rules that read the import graph; each gap of AD-454 and a part in another component than
its library give UNKNOWN for each rule of the run. A contract with a symbol selector or an
`interface_boundary` rule is a profile limit: each Dart rule is UNKNOWN (AD-468).

**Open false-PASS class (Python, shared with 4.0.1).** A third-party function can import a module
from a string, for example a plugin loader, a framework that reads a dotted path from settings, or
an object deserializer. The survey does not know such a function, so it does not see that edge.
A forbidden or cyclic dependency that only such a call makes can give PASS. Release 4.0.1 has the
same hole. This is an open defect, not an accepted limit. The survey covers the names of AD-450
point 7: the standard-library doors, the import state and the builtins that run text.
The Rust core is the only decision path (AD-432). There is no Python fallback.
Saved results do not carry host verification; dependency scope proofs replay as UNKNOWN with `dependency_scope_runtime_unverified`.
Windows ARM64, musllinux aarch64, Linux ppc64le/s390x/armv7 and BSD have no shipped binary.
The colocated digest detects file changes. It does not protect against an attacker with install-write access.
Python and Dart descriptions below apply to 4.0.1, not main.
Sections that name `check`, `explore`, baselines or the Python engine describe the engine before AD-432.

## The core path on main

- No release carries the core binary. A platform wheel of `main` carries it (`make native-wheel`),
  and a build without the core refuses. Run `main` from a source checkout after `make core`.
- The core decides on Windows since AD-442, and the installed Windows wheel must equal the core of
  the checkout. A release from `main` is open (AD-476): it publishes the sdist and the six platform
  wheels that Full builds and runs. The Windows wheel writes no report file (see `report --output`).
- `check`, `init`, `explore`, `guide`, `story`, `view` and `studio` give the typed refusal
  `not_on_this_development_line`, exit 2. Interactive reports, `architecture.json`, saved and focused
  reports, baselines, amendments and `--write-graph` are refused by option name.
- `report --output PATH` writes one static HTML page or the JSON frame (`--format json`). It has no graph.
  The parent must exist. Safe file output needs POSIX directory handles; Windows refuses `--output` with exit 2 (`io_error`), writes no file and keeps the frame.
- A rule kind without a port in the core is UNKNOWN with the gap `rule_kind_not_ported`. The run exits 2.
- The core does not compare `declarations.uml` with the source facts. The UML target row is always
  UNKNOWN (`no_receipt`), so the run exits 2. A conflict that 4.0.1 shows as FAIL is UNKNOWN (AD-470).
- A collection gap makes each rule UNKNOWN whose reading it can change. A manifest edge that the core
  proved can give a `requires` FAIL beside such a gap.
- `validate` and `report` read explicit `inside` mounts through the bounded core tree reader.
  Unsafe, linked, missing or invalid mounts stay UNKNOWN. Unproved tree rules keep their named gaps.
  A safe mount path that is absent, unreadable or not a contained regular file gives
  "mounts inside contracts that the shell has not sent". This names missing input, not an unported tree rule.
- The core checks contract hygiene on `validate` and `report` (AD-466). It reads and binds each cited
  provenance file. A file that it cannot read refuses the contract. A missing, repeated or stale marked
  graph, and the reference, rationale, responsibility, closed-world and `public_api` defects of 4.0.1,
  give a row that keeps the run from PASS. A cited path must be in normal form. A contract with an
  `interface_boundary` rule, `declarations.compat` or `declarations.measurement_budgets`, and a
  mounted contract with an `allowed_dependency` rule, get a named gap: these checks are not ported.
- Source that nests deeper than the parse work limit is the typed refusal `core_error` with `parse_work_limit`.
- A `collector_argv` in `archkeel.toml` is refused. The core starts only its own collectors.
- The survey refuses a root with more than 1 GiB of file bytes or more than 100,000 entries, by name.
  Below a directory with a `CACHEDIR.TAG` file that starts with the standard signature, the survey
  counts the depth but not the file bytes, and it counts the entries against a separate limit of
  1,000,000. So Cargo `target/` output does not use the byte limit or the entry limit of the source.
  A root with more than 1,000,000 entries below such directories is refused by name.
  A tool that writes build output without this file gets no exclusion.
- The exclusion selects no source. A Rust module that a `#[path]` attribute places below `target/` or
  below another tagged directory gives UNKNOWN, exit 2, with "impossible collection coverage counts".
  An `include!` of a generated file is a `collection_gap`. A TypeScript source below a tagged directory
  is still collected.
- The shell trusts the rule rows of the core binary that it located. It checks the root, the commit,
  the dirty state, the configuration and all contract file digests against its request (AD-438).
  A nested file changed since the request started is refused. Keep the snapshot unchanged during a run.
- ArchKeel checks only its Rust source in `native/` with the core: 63 rules PASS, 1 FAIL, 19 UNKNOWN,
  pinned in `native/expected-gaps.json`. The Python shell and the tools have no architecture contract.

Archkeel observes one static snapshot, not runtime behavior, data flow, performance
or responsibility fulfillment. A rationale proves recorded intent, not truth.
Determinism is measured for a machine/runtime, not across every platform.

## Git execution of the core path (F4; slice 5)

The core path uses fixed system Git, but `git status` still reads the scanned repository's `.git/config`.
A configured `filter.<x>.clean` can execute a command during status. Do not scan untrusted Git configuration.
Disabling repository-configured execution is deferred to slice 5; the fixed executable does not prevent it.
See [AD-422](architecture/decisions/ad-422-core-only-validation-renders-the-scan-frame.md).

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
[boundary tests](https://github.com/rapiddweller/archkeel/blob/4.0.1/tests/test_boundary_types_facades.py) and [rules](rules.md).
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
inside a frame they name another window, so the edge can go to a global of the page above. A chain
of these names (`window.self.x`, `top.window.x`, `parent.top.x`) is read like one of them (#1007).
A write through them (`top.x = 1`) publishes nothing, but it blocks each proof of the global `x`
([AD-460](architecture/decisions/ad-460-a-write-through-any-alias-of-the-global-object-blocks-a-global-proof.md)).
A write `o.x = …` blocks the global `x` unless `o` is a local new value or the `this` of a
constructor, a field or a static block. An unknown key on a window value, a window value that
escapes, and code from a text block every global proof of the project.
Open false PASS, not accepted (AD-460): a window value that reaches a computed write through a
parameter, a call result or a property (`function f(w) { w[k] = v; }` with `f(document.defaultView)`);
an extracted class method that writes `this[k]` and runs as a callback; a computed call with a key
built at run time on a parameter, an import, a property or a global function (`Object[k](text)` with
`k` equal to `constructor`); a reflection call with a run-time key; and DOM code from
text outside the named triggers (for example a `src` or `href` of `javascript:` built at run time).
Older classes stay open too: a prototype change through a call
(`Object.defineProperty(EventTarget.prototype, …)`), a member patch of a platform object that is no
window (`JSON.parse = …`, `document.open = …`), a use through `opener` or
`document.defaultView`, and a write in a file outside the scan roots or under `exclude`.
The native TypeScript collector reads a file up to 4 MiB. Above that size it gives UNKNOWN for
the file, where the Python collector reads the file and can give FAIL. The two collectors give
the same facts only for files under the limit.

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
PASS, not accepted (#1020): an item that a function-like macro generates without a recorded path.
The independent token inventory remains open (#1026); it must detect tokens that a macro reader loses.
Attribute macros and unproved derives have named expansion gaps on every scanned syntax position.
Each gap names the source module and leaves the target unseen. It blocks affected rules through
the existing pair-gap scope proof. Inert built-ins and `cfg`/`cfg_attr` cannot be shadowed by a `use`.
Prelude attribute macros, including `test`, `global_allocator` and `derive`, need a namespace proof.
An explicit binding, an unproved glob or an enclosing `extern crate` withholds that proof.
A shadowed `derive` proves neither its listed derives nor their helper registrations.
Tool attributes need their tool prelude. Unknown attributes and unproved prelude macros keep a gap.
Built-in derives need a macro-namespace proof. Block-local and enum-variant globs cannot shadow
a module-level derive. Workspace-module globs need a closed export proof; unseen macro output
and external globs keep the gap. The native workspace has no proc-macro crate.
A glob that can reach macro output withholds built-in derive identity; use explicit imports.
One typed table models `serde::Serialize`, `serde::Deserialize` (1.0.229), and
`schemars::JsonSchema` (1.2.3). File use records must prove the identity without a glob or shadow.
The library and its derive implementation need unique crates.io registry identities in `Cargo.lock`.
Path/git sources, workspace members, patches, replacements, stale locks and source configuration
files withhold this proof. Renamed registry dependencies are followed through the manifest.
Any `.cargo/config` or `.cargo/config.toml` below a scan root or on its repository ancestor path
withholds the model, including files in nested non-crate directories. The search follows no symlink.
It withholds the model beyond directory depth 128 or one million entries, and at unreadable directories or directory links.
Open false PASS, not accepted (#1020): build settings outside the repository can replace registry code.
The snapshot cannot see `$CARGO_HOME` configuration, `CARGO_*` source settings or the build invocation environment.
Such an override can make an unseen expansion pass silently. This is a limit, not a proof of that build.
These derives generate impl code using their own crate, written types, and documented helper paths.
Every helper path, type and bound is read as a path use of the item's module, including bare names.
Unknown helper keys, unsupported conditional metadata, macro values and invalid syntax keep a gap.
The model covers written dependencies, not trait dispatch (#1004). Other versions keep a gap.
See [AD-424](architecture/decisions/ad-424-known-registry-derives-need-identity-and-helper-proofs.md),
the [Serde container](https://serde.rs/container-attrs.html), [field](https://serde.rs/field-attrs.html)
and [variant](https://serde.rs/variant-attrs.html) docs, and the
[Schemars helper docs](https://graham.cool/schemars/deriving/attributes/).
An unclassified attribute or helper has a gap. A file with invalid UTF-8 has a named read gap.
Not seen, and the verdict can be PASS:
a path into another crate that goes through a `pub use` of its root. A rule on a module pair
forbids a direct use; a use through a re-export is seen by the layer and cycle rules (AD-357). For
`pub use crate::b::make;` in `c` and `use crate::c::make;` in `a`, the edge of `a` goes to `c` and
the edge of `c` to `b` (a `reexport` record); a module cycle through such a `pub use` gives FAIL
(`tests/test_collector_false_pass_rust_impls.py`). The same holds for `pub use crate::b::*;` in `c`
and `use crate::c::*;` in `a`. A macro call with a path in its body, an exported `macro_rules!`, `include!`, a `cfg` that gates a `mod` or
`use` (except `cfg(test)` and a declared feature), a `path` attribute that is not a literal, an
unmodeled attribute macro on any item, brackets nested deeper than 256 and a module deeper than 64 levels
make the scan UNKNOWN, and so does a path whose first segment is a crate name that the file also
declares or imports (`::` makes it the crate). A reachable crate name that appears in a macro body, an attribute stream or a string, with no edge to that crate in the file, is UNKNOWN too. A local variable or a field with that name is not. A dependency that a Cargo.toml declares (normal, dev, build, also the underscore forms and
`[target.*]`) is a crate edge even when no source uses it: a crate cannot use a crate that it does
not declare. A dependency table that the reader does not know is UNKNOWN. A `macro_rules!` that
stays in the crate is read as code of its file, and an exported one is UNKNOWN. A planned crate
has no component in the native contract until it has code. Test code (`cfg(test)`, `tests/`, dev-dependencies) counts as production
code until the host key `[scan] exclude_test_sources` is set. With the flag, a `cfg(test)` or `cfg(all(test, ..))` item, module,
impl or trait member and `let` or macro statement, a `#[test]`, `#[x::test]` or `#[rstest]` function, and the `tests/`, `benches/` and `examples/` targets
leave the reply. A `cfg` on a field, a match arm or an expression stays in scope, and so does a test attribute that this list does not
name (`#[test_case]`). A production target or module file in a test directory is UNKNOWN, because the host refuses a reply that selects it. A platform wheel carries the core, which links the collector; a package without the core
refuses with `core_binary_not_found`
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

## The Rust core

The Rust core (`archkeel-core`, [AD-378](architecture/decisions/ad-378-a-rule-passes-only-with-the-scope-proof-of-its-own-model.md)) decides `validate` and `report` on main (AD-432). The comparisons with "Python" below are with the deleted Python engine; they stay as the record of what the core proves differently. Its scope proof is stricter than Python in these cases, each a named gap, never a PASS:

- A gap between two modules that the contract allows: Python drops it for the Rust profile only. The core keeps it for each rule whose reading it can change (UNKNOWN), for example a whole-component side of a `forbidden_dependency` rule that the drop rule does not see. For another profile both engines keep the gap ([AD-384](architecture/decisions/ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md), [AD-418](architecture/decisions/ad-418-a-dropped-pair-gap-holds-the-rules-it-can-change-and-a-scoped-requires-needs-its-runtime.md)).
- `interface_boundary` imports need a known binding and a witnessed publication route ([AD-428](architecture/decisions/ad-428-the-interface-import-verdict-needs-a-known-binding-and-publication-proof.md)). Direct witnessed names and known static module objects can pass. Named type-only imports also need a merge-free declaration and a direct export witness, or one same-name named type re-export hop ([AD-434](architecture/decisions/ad-434-named-type-publication-needs-a-direct-witness-or-one-same-name-hop.md)). Aliases, star exports, namespaces, default exports, merged declarations, longer routes and missing witnesses remain named gaps. A known direct private type import still fails. Public-interface lifecycle validation remains outside this port until D2.
- A symbol-level selector in a reply with `script-globals-v1`: one profile reads such selectors. 4 rules (PASS in Python).
- A runtime requirement that is not `>=X`, and a `forbidden_construct` rule that selects no module: no corpus case.
- `complete_requires` ([AD-380](architecture/decisions/ad-380-the-core-decides-the-direction-rule-kinds.md)): a coverage gap that the dependency scope proof of the host can accept is a named gap for this kind, for a reply of the one runtime that can carry the proof. For any other runtime the gap is a fact, as in the host ([AD-418](architecture/decisions/ad-418-a-dropped-pair-gap-holds-the-rules-it-can-change-and-a-scoped-requires-needs-its-runtime.md)). The receipt reads the scan roots of the request ([AD-384](architecture/decisions/ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md)); a contract with a selector rule (its source is a receipt scope) is a named gap.
- The cycle receipts and the receipt of `complete_requires` map a module file to its directory only for a profile with a proven import closure (`Layout::ProjectFiles`); any other profile is a named gap.
- A `layer_order` rule without the source of the contract bytes in the request: a named gap. The core does not read the contract file again after the shell read it.
- A `requires` symbol port in a reply without the symbol feature: the import is left out, as in the store-accepted profiles.
- The contract path in the dual-run request is the word of the caller. It sets only the evidence id of the `layer_order` rows, never a verdict: the model binds the bytes to the parsed contract by their digest, not the path.

The core decides one rule kind set where Python does not ([AD-384](architecture/decisions/ad-384-the-core-decides-the-cycle-rules-and-scopes-each-pair-gap-to-the-rules-it-can-change.md), "core decides, Python does not"). Python makes every rule UNKNOWN for a pair gap that it keeps. The core holds only the rules whose reading the gap can change, and it passes the others. The run stays UNKNOWN and names each kept gap. The frame lists each such rule in `beyond`, and the harness shows it as a named difference. The corpus has 22 such rules in 17 cases (`BEYOND_CASES` in `tests/test_native_core.py`). Four limits apply:

- The Rust collector does not mark an external `pub use` as a re-export. So a gap into a module with any external import holds `external_dependency_scope` and `complete_external_scope`.
- The gap scope reads the edge model of the collector, as Python does. A glob that brings in a trait through a `pub use` chain `b -> d` gives the gap `a -> b`, not `a -> d`, so a rule on `a -> d` passes (review N2 of #1084). With the explicit call both engines record only `a -> b`.
- A method call can reach a member in another crate through any crate of the Cargo closure of the caller, and the collector lists such candidates. Two forms give no candidate, also inside one crate: a trait method (`impl Trait`, `Box<dyn Trait>`, the class #1004) and a method in the file of its type, called on a value that the caller does not name (for example the return value of a function of another crate). On `native/` the rows `NATIVE-NO-CORE-TO-TYPESCRIPT` and `NATIVE-NO-CORE-TO-RUST` hold only because a test pins the import records of the reply from `collect` to each collector crate. Both are open false PASS classes of the edge model ([AD-418](architecture/decisions/ad-418-a-dropped-pair-gap-holds-the-rules-it-can-change-and-a-scoped-requires-needs-its-runtime.md)).
- A PASS beyond Python is only as strong as the edge model of the collector. The open false-PASS classes #1004 (a trait `impl` in a third module) and #1020 (an item that a macro makes) give no edge and no gap. Where Python gives UNKNOWN only for a kept gap, the Python UNKNOWN hid them; the core PASS does not ([AD-418](architecture/decisions/ad-418-a-dropped-pair-gap-holds-the-rules-it-can-change-and-a-scoped-requires-needs-its-runtime.md)).

The dual-run request is a test protocol. Its `collector_argv`, `pinned` and `standard_library` fields are the word of the caller, not evidence: a wrong producer or an extra standard library name can give a PASS that Python does not give. The request of M1 must not take them from a caller: the shell starts the pinned collector, checks its digest and fills the producer and the standard library from its own profile table.

## Scan work bounds are not process-memory bounds

[AD-420](architecture/decisions/ad-420-bound-parse-work-before-an-in-process-collector-reads-bytes.md)
bounds per-file work, bracket nesting and distinct input, not process memory.
The limits are 4 MiB per file, 8,388,608 byte/token units, 512 bracket levels and 64 MiB distinct scan input.
Flat statement and expression chains do not count as bracket nesting.

The review measured an accepted TypeScript scan of 15 files of 4 MiB, about 63 MiB input, at about 10 GiB RSS.
Main is within 3 %. The collector retains about 160 RSS bytes per input byte across files.
The syntax tree or source of each file must be released when its facts are taken.
Single-file peaks reached about 1.0 GiB for 4 MiB of TypeScript and 1.2 GiB for a 4 MiB Rust array.

A 4 MiB Rust long expression aborts the core process with SIGABRT, on main too.
That run produces no verdict. It must become a typed refusal instead of an abort.
These remain open in #1111. The target is a 300 MiB peak RSS line plus a stated RSS/input factor.
The selected 300 MiB regression probes do not prove this target for every accepted input.

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
before #1072 is closed. [AD-402](architecture/decisions/ad-402-the-python-raise-site-inventory-keeps-unproved-paths-open.md)
refuses the 100 reviewed sources and checks the H1–H5 scope/name families.
The source inventory has 257 message witnesses and 1,077 unproved
rows. A matching message does not prove every compiler path. Indirect errors, dynamic messages,
AST-only failure reachability, memory exhaustion and interpreter settings still need proof.
Issue #1072 stays open. The oracle uses the default recursion limit of 1,000, not the host's 20,000.
Native checks every static-block branch and reserves an async cleanup block. CPython can remove
some branches. Native also bounds 3.11 `elif` chains at depth plus clause count 900. These bounds
can be stricter, with a named gap. Neither measured corpus has a new refusal on any supported minor.
Two parser false-refusal classes remain. On 3.13/3.14, Tangut named escapes such as
`'\N{TANGUT IDEOGRAPH-17000}'` get `Got unexpected unicode` from Ruff, although CPython accepts them.
On 3.12, a single-quoted f-string format spec with a literal newline gets the named newline gap,
although CPython accepts it. The annotation-comprehension walrus false refusal (F2) on 3.14 is fixed.
Ordinary annotation comprehensions can bind; type-parameter and type-alias scopes still cannot.
The CPython source hash/extractor comparison is not gated: no target or workflow supplies
`ARCHKEEL_CPYTHON_SOURCES`. Without it, the test visibly skips with its reason.

## Scope and nested contracts

A run covers only configured roots and namespace. Adjacent tests need another
configuration, contract and output path. Their product imports are external, so
product-module boundaries cannot be expressed from that namespace.

Only explicit `inside` mounts evaluate child contracts. Invalid mounts prevent
complete observations and baseline/graph writes. Child public interfaces govern
siblings, not the parent's outward API. Unmapped scope prevents proof. Use
[reference](reference.md) for path and gate semantics.
