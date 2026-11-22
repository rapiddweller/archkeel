# Known limits

Every false-PASS fix PR updates its row in this file in the same PR.

## Supported projects on main

What each language decides on main. The README quotes this block, and `tests/test_readme_showcase.py` keeps the two equal.

<!-- tiers:start -->
ArchKeel collects source evidence for Rust, TypeScript, Python and Dart.
Rule coverage depends on the language and the available evidence.
Python and Dart support import and interface boundary checks.
Python also checks direct function calls for `call_owner`.
Dart checks cycles when the package map is complete.
Unsupported or unproved cases remain UNKNOWN.
Python and Dart can check named imports against a declared `interface_boundary`.
<!-- tiers:end -->

The details follow.

### Collector audit at `323f09881`

The 2026-11-17 audit uses the core built from `323f09881`. Each plant is synthetic.
Run `make core`, then `uv run --locked archkeel validate --config <plant>/archkeel.toml --json`.
The issues below contain the fixture files and exact output. Each reported false PASS exits 0.
The issues record follow-up work for these findings.

| Class | Plant | Result at `323f09881` | Follow-up issue |
|---|---|---|---|
| Rust field receiver | `p.f.m()`: an inherent method in the file of its type, called through a public field of a typed parameter; no edge and no gap (AD-418) | false PASS | [#1571](https://github.com/rapiddweller/archkeel/issues/1571) |
| TypeScript DOM code | an `open` result, `document.open`, or a dynamic link and click | false PASS | [#1526](https://github.com/rapiddweller/archkeel/issues/1526) |
| TypeScript prototype patch | replace `EventTarget.prototype.dispatchEvent`, then use it on `window` | false PASS | [#1527](https://github.com/rapiddweller/archkeel/issues/1527) |
| TypeScript unread source | imports in Vue, Svelte, Astro, MDX, inline HTML and `.es6` | false PASS | [#1528](https://github.com/rapiddweller/archkeel/issues/1528) |
| TypeScript installed source | a package in `node_modules` imports project source | false PASS | [#1529](https://github.com/rapiddweller/archkeel/issues/1529) |

These tested forms no longer give a false PASS. The first ones were measured at the audit base;
the last two were fixed after it and are checked on main at `157dc8851`:

- Python `import app.lib; app.lib._priv.secret()` gives FAIL. An escaped module binding gives
  UNKNOWN with an unproven publication route. The fixtures are in
  `tests/python_interface_module_plants.py` (AD-708, #1415).
- A scanned writer that uses `marker.__globals__["f"] = secret` gives UNKNOWN with
  `dynamic_import: __globals__`. A dictionary returned by an outside library remains #1521.
- For Python lazy annotations, direct `setattr`, a class decorator, a module `globals()` write,
  a method's `global` write and metaclass `__prepare__` each give a named UNKNOWN. When the
  `requires-python` range allows 3.14, a `__slots__` entry and an attribute store of the same name
  in a file of the scan or a non-test file of the repository give `lazy_class_namespace`; a
  `setattr` with a computed name gives it for each name (AD-802, #1523). The fixtures are in
  `tests/test_collector_false_pass_python_lazy_annotations.py`. A bare class annotation that declares a UML attribute
  (AD-748) follows the same rule, and a `__slots__` entry of its name holds it on every version
  (#1714).
- A Rust `macro_rules!` call that adds an unanchored `Display` impl gives UNKNOWN with a pair
  gap. The fixture is `PLANTS["an impl that a macro of b generates"]` in
  `tests/test_collector_false_pass_rust_orphan_impl.py` (AD-662).
- A git URL of the same repository, an outside Cargo patch, a command-line patch and a repository
  patch each give UNKNOWN with a crate-pair gap (AD-704, #946).
  `tests/test_collector_false_pass_rust_redirect.py` holds the four compiling fixtures.
- A Rust path through a re-exported name of a module gives FAIL: `crate::c::other::b::g()` where
  `c` re-exports a module, the crate root, an alias of `extern crate self`, another crate of the
  workspace, or brings the name in by a glob (also `use base::*; hidden::g()`), and an `extern crate
  base as other;` in a module, at the crate root, or through the extern prelude (#1711). A route that a
  macro call writes, or one over the hop limit, gives UNKNOWN. The 22 compiling fixtures are in
  `tests/test_collector_false_pass_rust_root_reexports.py` (AD-772, #1517).
- A patch of a platform prototype (`Object.defineProperty(EventTarget.prototype, …)`, a prototype
  that is passed on, `ev.target.__proto__ = …`) gives UNKNOWN with a source-resolution gap
  (AD-768, #1527). `tests/test_cli_native_prototype_patch.py` holds 18 forms.
- DOM code from a text (`document.open()` and `write`, a document that is passed on, a link,
  frame or form address that is no literal, `insertHTML`) gives UNKNOWN with a source-resolution gap
  (AD-792, #1526). `tests/test_cli_native_dom_code.py` holds 24 forms.
- Direct aliases of `Object`, `Reflect`, `location` and `open`, and direct timer aliases, give
  UNKNOWN with a source-resolution gap. This does not prove arbitrary value flow safe.
  `tests/test_cli_native_global_forms.py` checks the direct reflection and navigation aliases.
- A TypeScript source that TSConfig drops gives UNKNOWN with a named file gap (AD-488).
- An installed package whose code imports project source gives UNKNOWN with a gap of each module
  that imports the package (AD-798, #1529). `tests/test_cli_native_installed_source.py` holds the
  forms.
- Explorer boxes of a FAIL run that has a rule the core does not port show UNKNOWN, no PASS box,
  cell or edge: only a run that decides every rule keeps PASS boxes (AD-730, #1507, PR #1569).
  `test_a_fail_beside_an_unported_rule_draws_no_pass_box` in `tests/test_cli_report_page.py`.
- A TypeScript value read with a run-time key and called later (stored, passed, used as an
  argument, in an array or object, through `call`, `apply` or `Reflect.apply`) gives FAIL or UNKNOWN
  (AD-758, #1525 and #1547, PR #1574). The plants are in
  `tests/test_collector_false_pass_ts_lookup.py`; a value that is only tested keeps its PASS.

Main supports Rust and TypeScript projects, and the import rules of Python (AD-450) and Dart (AD-468) projects.
The linked Python collector also proves direct function calls for `call_owner` (AD-1002).
An open import route keeps call identity unproved. An unrelated open call does not hide a proven violation.
A dynamic import, an import-system change and the other gaps of AD-450 can hold rules that read them.
A contract can declare the reach of an `eval`, `exec`, `compile`, unpickler, loader or `__import__`
site; a PASS then holds only under that premise and says so (AD-664). A trojan horse module binding and a
pickler have no declarable reach, and a TypeScript run-time key whose gap blocks the free standard
names cannot apply.
A re-export of a package is read through its uses: a name of a package that another module
uses as a value escapes the package, unless its origin cannot be a module of the scan (AD-530). A
read of `__globals__` is no gap when the dict only feeds a lookup of a literal key; library code
that gives the dict back is not seen (AD-530).
Python construct rules stay UNKNOWN when the collector cannot prove that it sees every site.
For `type_ignore`, a single-line call with a plain or dotted name, assignment to one name,
annotated name, or return with a value can carry an exact trailing comment. Other unread type comments
keep the rule UNKNOWN (AD-780, AD-868, AD-872, AD-908, AD-942, AD-990, AD-997). `interface_boundary` and symbol-level
`through` ports are decided from the publication route of each named import (AD-504); the hygiene
checks `interface.*` prove a use of a `public` entry from the imports and name `interface.usage_unknown`
where only a declared facade signature could reach it (AD-514). A Dart project gets PASS or FAIL
only for rules that read the import graph; each gap of AD-454 and a part in another component than
its library give UNKNOWN for each rule of the run. A symbol selector or an `interface_boundary`
rule holds only the rules that read it (AD-500). A Dart cycle rule (`no_component_cycles`) has its
receipt when the package map is complete (AD-800; 4.0.1 gives no Dart cycle receipt). The survey
reads the dependencies, overrides, `workspace` and `resolution` of the root `pubspec.yaml`: an
import of a package that the map does not prove hosted, SDK or remote git is a gap of its library
(`DartLocalPackage`, `DartUndeclaredPackage`), and a local package that no library imports adds no
gap. The package of the scan is the nearest `pubspec.yaml` at or above its roots (AD-808): a member
reads the workspace root above it for its members. A member whose workspace root is outside the
snapshot, or not readable, gets that gap at each `package:` import (a snapshot that omits the workspace root). The Dart collector reads bounded YAML. It keeps a
whole-scope gap for a pubspec that it reads only word by word, an unsupported YAML form, and a
workspace that it cannot prove disjoint from the scan roots (AD-542). Loader and mirror identifiers and non-own relative
package roots also give gaps (AD-562).

**Dart import premise (AD-542).** Code outside the scan roots does not load or run scanned code
from a name passed as data. The current report does not yet print this premise. The stated-premise
mechanism must land before this decision is merged.

**Open false-PASS class (Python, shared with 4.0.1).** A third-party function can import a module
from a string, for example a plugin loader, a framework that reads a dotted path from settings, or
an object deserializer. The survey does not know such a function, so it does not see that edge.
A forbidden or cyclic dependency that only such a call makes can give PASS (#1519). Release 4.0.1 has the
same hole. This is an open defect, not an accepted limit. The survey covers the names of AD-450
point 7: the standard-library trojan horses, the import state and the builtins that run text.

The Python collector does not follow a value from an unknown object to a loader. For example,
a call of a method on an unknown value can load any module. A runner of the `code` module
(`interact`, `InteractiveConsole`, `InteractiveInterpreter`) on a name `code`, on a name assigned
from an attribute `code`, or on an attribute `code` of any value is a dynamic-import gap (AD-762).
Any other method of an unknown value is not read; a forbidden dependency reached only through it can
give PASS. This is an open false-PASS class, not an accepted limit. A call of a
value that an import from outside the scan and the standard library gives, with a string that names
a module of the scan, is a gap of the edges of its module (AD-760); a loader handed in as a
parameter is the same open class.

**Python `symbol_placement` (AD-726, AD-728, #1713).** A PASS needs the receipt "no written
class" for each selected module outside the allowed sources. A call that can create a class at run
time withholds the receipt, and the rule is UNKNOWN with the site: "a call can create a class at
`path:line (callee)`". Such a call is:
- a factory of the standard library, by the import that binds its name: `Enum` and the other
  `enum` classes, `namedtuple`, `NamedTuple`, `TypedDict`, `make_dataclass`, `types.new_class`,
  `ABCMeta`, `__build_class__`, `type` with three arguments;
- a call in the shape of a metaclass call (`M("Name", (...), {...})`);
- a well-known library factory, in any use of its result, also a plain return: `attrs.make_class`
  and `attr.make_class`, `pydantic.create_model`, `marshmallow.Schema.from_dict`,
  `msgspec.defstruct`, `sqlalchemy.orm.declarative_base` and `registry().generate_base`. The table
  `FACTORIES` in `survey/stable/class_inventory.rs` holds the list and says how to extend it;
- a call whose result the module calls or passes as the class of `isinstance` or `issubclass`.

The plants are in `tests/test_collector_false_pass_python_placement.py`. Open: the factory of
another library, whose result the module only returns, gives no such site. The rule then reads the
module as holding no class. This is an open false-PASS class, not an accepted limit: a factory
joins the table with a plant whose Python truth is a class.

**Python module and class bindings (AD-642, #1360).** A module- or class-level binding such as
`for site in sites: site.id` can retain an `import_system_change` gap. These namespaces resolve
names in execution order. The survey does not yet prove the binding at each read.

**TypeScript: the code of an installed package (AD-798, #1529).** The collector reads the static
imports of each installed file that an import of the scan reaches, and of each installed file that
those reach. A package that the snapshot does not hold gives the unresolved-import gap, as before.
It resolves a path directive from its own file and a module augmentation as an import, reads a
repaired file by its quoted names too, and reads each file of an installed package whose entry the
resolver cannot decide (`typesVersions`). An import that resolves to a file outside `node_modules`,
another name that the resolver cannot decide, and an installed file that the collector cannot read
are a gap of each module whose import reaches that file. So the plant
`src/b/node_modules/local/index.ts` with `import { a } from '../../../a/a'`, imported as `local`
from `src/b/t.ts`, gives UNKNOWN. Release 4.0.1 gives PASS. A loader with an unknown target in a
runtime file of the closure (a computed `require` or `import()`, a call of `createRequire`) is a
reach too (AD-812, #1749). A preload that a repository data file names is read with the AD-788
writer guard. A preload that patches the module loader withholds every route (AD-845, #1750).
A closure of more than 20 000 installed files is a gap of each importer.
The Rust core is the only decision path (AD-432). There is no Python fallback.
Saved results do not carry host verification; dependency scope proofs replay as UNKNOWN with `dependency_scope_runtime_unverified`.
Windows ARM64, musllinux aarch64, Linux ppc64le/s390x/armv7 and BSD have no shipped binary.
The colocated digest detects file changes. It does not protect against an attacker with install-write access.
Sections about the Python engine and its `check` command describe release 4.0.1.
See the [CLI reference](reference.md) for current commands and baselines.

## The core path on main

- Studio auto-detects one standalone root-level Python script with an identifier as its filename
  when no other supported area is found. Multiple standalone scripts need an explicit scan or
  a supported [Python project layout](onboarding.md).
- No release carries the core binary. A platform wheel of `main` carries it (`make native-wheel`),
  and a build without the core refuses. Run `main` from a source checkout after `make core`.
- The core decides on Windows since AD-442, and the installed Windows wheel must equal the core of
  the checkout. A release from `main` is open (AD-476): it publishes the sdist and the six platform
  wheels that Full builds and runs. The Windows wheel writes no report file (see `report --output`).
- `init` drafts a contract from the folder layout of Python packages, a Cargo workspace or a
  `package.json` workspace (AD-626, AD-638). Each decision is a `TODO`. `validate` and `report`
  run `init` when `archkeel.toml` is missing and writing is allowed.
- `studio` opens the local Explorer. Existing scripts can use `explore`. Interactive, saved and
  focused reports, `architecture.json`, amendments and `--write-graph` are refused by option name.
  `--baseline` and
  `--write-baseline` are served ([reference](reference.md#baselines)).
- `report --output PATH` writes one static HTML page or the JSON frame (`--format json`). It has no graph.
  The parent must exist. Safe file output needs POSIX directory handles; Windows refuses `--output` with exit 2 (`io_error`), writes no file and keeps the frame.
- A rule kind without a port in the core is UNKNOWN with the gap `rule_kind_not_ported`. The run exits 2.
- The core compares the module and import part of `declarations.uml` (AD-494) and the symbol part
  for TypeScript (AD-512) and Dart (AD-796) and, for the declarations only, for Python (AD-518).
  Rust gives no symbol facts, and Python gives no site (base, call, reference, `creates`,
  `instance_of`), so a relationship of a Python target is UNKNOWN with the cause "the python
  collector states no symbol sites" (H-uml stays UNKNOWN). A Dart class inventory is `partial` when
  a mixin application, a part of the library or a project extension can add a member that the class
  body does not show. A Dart site binds only a declaration of the snapshot: a member that only a
  base outside it can declare stays unresolved. A Python declaration is written only for a class, function, method
  or class attribute that one plain statement binds once; a second binder (`if`, `try`, `for`,
  `with`, `del`, `global`, walrus, `match`, star import), a decorator other than the builtin
  `staticmethod` or `classmethod`, a keyword or an unproven base, a hazard site or a write from
  another module gives no record, so the name is absent (UNKNOWN). A class that a base which may be
  a class writes to (`type.__setattr__`, `cls.x = v`, `self` of a metaclass), or whose name is
  passed, stored or returned, keeps no member. A bare annotation declares a UML attribute only
  when its type is an unshadowed builtin (AD-748). A value that is no literal and a mangled `__x`
  are no attribute. A module-level value, a function inside a function and a
  text other than a name, a dotted name, `None`, `True` or `False` in an annotation or a default
  give none. A write from an extension source of the repository that names the module escapes it
  (AD-770). Open: a write through `globals()` of another module.
  Every Python member list is `partial`. A target
  in an inside contract and an external import target keep it UNKNOWN too. A target that 4.0.1
  passes with symbol facts (H-uml) exits 2. A FAIL for a conflict, a missing base or an
  extra element of a closed scope is true whatever the coverage, so it stays in an incomplete run.
  A missing symbol, call or reference is UNKNOWN, never FAIL. A planned member that the matched class lacks is
  UNKNOWN too, where 4.0.1 gives FAIL (AD-512): the collector states no complete member table. A closed scope without an extra
  element passes only when it is the scope of a class, an interface or an enum over member kinds
  and the collector states each listed member inventory complete (AD-747). TypeScript states it
  complete when the body shows every member of the type; Python and Rust inventories are always
  partial, and the row names the reason of the collector. A closed module scope and a closed
  scope over relationships stay UNKNOWN: no fact states a complete module or site inventory. A dropped pair gap that
  touches a module of the target holds the UML row. A Rust UML row has no 4.0.1 comparison and
  rests on the scope proof alone.
- A collection gap makes each rule UNKNOWN whose reading it can change. A manifest edge that the core
  proved can give a `requires` FAIL beside such a gap.
- `validate` and `report` read explicit `inside` mounts through the bounded core tree reader.
  Unsafe, linked, missing or invalid mounts stay UNKNOWN. Unproved tree rules keep their named gaps.
  A safe mount path that is absent, unreadable or not a contained regular file gives
  "mounts inside contracts that the shell has not sent". This names missing input, not an unported tree rule.
- The core checks contract hygiene on `validate` and `report` (AD-466). It reads and binds each cited
  provenance file. A file that it cannot read refuses the contract. A missing, repeated or stale marked
  graph, and the reference, rationale, responsibility, closed-world and `public_api` defects of 4.0.1,
  give a row that keeps the run from PASS. A cited path must be in normal form. An `interface_boundary`
  rule gets the interface lifecycle rows of AD-514. A contract with `declarations.compat` or
  `declarations.measurement_budgets`, and a mounted contract with an `allowed_dependency` rule, get
  a named gap: these checks are not ported.
- Source that nests deeper than the parse work limit is the typed refusal `parse_work_limit` (AD-735).
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
- ArchKeel checks its Rust source in `native/` with the core: 86 rules PASS, 0 FAIL, 0 UNKNOWN, 0 violations,
  pinned in `native/expected-gaps.json`. The Python shell and the tools have no architecture contract.
  This contract states each crossing as a module port (`through`)
  ([AD-588](architecture/decisions/ad-588-the-self-contract-states-layers-parts-and-crossings.md)).
  `boundary_types` needs type shapes, which only the Python collector writes (AD-550).

Archkeel observes one static snapshot, not runtime behavior, data flow, performance
or responsibility fulfillment. A rationale proves recorded intent, not truth.
Determinism is measured for a machine/runtime, not across every platform.

## Git execution of the core path (F4; slice 5)

The core path uses fixed system Git, but `git status` still reads the scanned repository's `.git/config`.
A configured `filter.<x>.clean` can execute a command during status. Do not scan untrusted Git configuration.
Disabling repository-configured execution is deferred to slice 5; the fixed executable does not prevent it.
See [AD-422](architecture/decisions/ad-422-core-only-validation-renders-the-scan-frame.md).

## A `sys.path.append` of the snapshot (Python, AD-538)

One write form is no gap: `sys.path.append(str(Path(__file__).resolve().parents[k]))` as a statement
of a module body, when the directory holds no module-like entry that the scan imports. The verdict
holds for a run from the snapshot tree. A copied, installed or zipped layout, a direct run of a
`.pyc`, and `run_path` with a relative path plus `os.chdir` give another directory. An entry that
appears in the directory after the snapshot, a writer outside the scan roots (`conftest.py`,
`sitecustomize`, an installed package), a name that only code outside the scan imports, and a
namespace that does not resolve to the scan root are not seen. `insert` and each other write of
`sys.path` stay the gap of the whole run. A read of `sys.path` as the source of a loop or a
comprehension, or as a subscript read, is no gap. Comparisons keep the gap (AD-894).

## Open false PASS, not accepted (Python `interface_boundary`, AD-504)

A use of a name through a module object (`import app.lib` then `app.lib._priv.secret()`) is the
import of that name: each attribute load through a module binding, and through each child module of
a chain, is a record of its own (AD-708). A module object that escapes (a bare load, an assignment,
an argument, a namespace attribute, a store) leaves the names of its import unread: the rule is
UNKNOWN for it. A name is read in its scope: a parameter or another local binding of the spelling is
another value (#1506), and a name that an import and another binding share may be the module.

The core gives PASS where Python binds something else at import time only under the stated
premise. 4.0.1 gives PASS for these forms too. Plants: `tests/python_interface_plants.py`,
`tests/test_collector_false_pass_python_writers.py`.

- A write to a package that the repository does not show, after its statements ran. The survey
  reads the code of the repository outside the scan roots (AD-770): a script or an extension source
  that writes a module of the scan, or names it beside a trojan horse, withholds its routes (UNKNOWN). A test
  file (`test_*.py`, `*_test.py`, a file below `test/` or `tests/`), a name built at run time from
  data, and code outside the repository (`sitecustomize`, an installed package, a `.pth` file) are
  the stated premise of the run: "Code outside the scan roots, including test code, hands in no
  module object of the scan and writes no binding of a module or class of the scan." In the scan, a
  write through `sys.modules` or a computed `importlib.import_module` is a survey gap, so the rule is
  UNKNOWN. A direct scanned read of another function's `__globals__` also keeps its named gap, and an
  outside library dictionary that hides an importer gives the gap of AD-760 (#1521).

## Open false PASS: a code object reached by a route that the collector does not read (Python, #1969)

A code object lets code build a function that imports any module (`type(f)(code.replace(co_names=...), {})`).
The collector gives a `dynamic_import` gap (a trojan horse site, AD-1053, AD-1058) for these routes:
a literal code attribute (`__code__`, `f_code`, ...), `getattr`, `setattr`, `delattr`, `__getattribute__`,
`__setattr__` and `__delattr__` with a name or a receiver that it cannot prove, each reference to one of
them that is no direct call (`g = getattr`, `map(getattr, ...)`), `vars(x)` and `x.__dict__`,
`attrgetter`, `methodcaller`, `inspect.getmembers` and `gc.get_referents`. No receiver is proven: `self`, `cls`, a class and a module are no proof. A lazy `__getattr__` table keeps its `getattr` sites, so its proven keys (AD-654) are dropped until a contract declares them. A loop over a literal tuple of names keeps its site (precision limit; a contract can declare it). A literal that names reflection (`__dict__`, `__getattribute__`, `__class__`) keeps its site; the dunders that hand out text (`__name__`, `__doc__`, `__file__`, `__version__`, `__all__`, `__module__`, `__qualname__`) do not.

Still open, with a plant that fails when it is fixed (`tests/test_collector_false_pass_python_open.py`):
- `dis.Bytecode(f).codeobj` hands out the code object without a name: #1969. Other standard library
  routes can exist; the collector has no list of them.
- The standard library imports a module that a string names: `logging.config.dictConfig` (`'()'` and
  `'class'` keys) and `unittest.TestLoader().loadTestsFromName`: #1970 (one issue for the list; the
  plants are in `tests/test_collector_false_pass_python_stdlib_importers.py`).

A declaration is trusted: the scan does not check `loads` or `covers` (AD-1052, AD-1056). The rule can give PASS under a declared reach while Python imports the module, when a covered module hands the bound name to an uncovered module (it re-exports the attribute, it imports the name under another name, or `covers` lists the importer itself); `main` gives UNKNOWN there only because it cannot read a declaration. This is the trust that `covers` states, and `tests/test_cli_python_trojan_horse_covers_trust.py` pins it. A covered module is trusted not to hand the bound name to an uncovered module; the scan does not check this. The report prints the number of covered modules of each declaration. Guidance for EE and CE: a unique alias of the bound name (`import pickle as _pickle_loader`) avoids almost all name hits and the long `covers` list.

Premise: code that writes raw memory (`ctypes`, `from_address`) can change a code object or a binding without any name that the scan reads. The scan does not read it; the run assumes that the scanned code does not do this.

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
A field `date: date` is one false UNKNOWN. Release 4.0.1 does not see these writes outside the class
body ([#775](https://github.com/rapiddweller/archkeel/issues/775)):
- On 3.14: `__slots__`, `setattr`, a class decorator, a write from another module, a module-level
  `globals()['object'] = Hidden`, and `global object; object = Hidden` in a method.
  The native collector reads a method annotation as lazy when the `requires-python` range allows
  3.14 and the module has no `from __future__ import annotations` (AD-802). A `__slots__` entry, an
  attribute store of the name anywhere in the scan or in a non-test file of the repository, and a
  `setattr` with a computed name give the gap `lazy_class_namespace`. The text output names the
  remedies: narrow `requires-python` below 3.14, add `from __future__ import annotations`, or
  remove the namespace write. The JSON and the report say them in words that name no language. A store in test code or outside the repository is the stated premise
  of the run (AD-770).
- On every version: a metaclass `__prepare__` that puts the name in the class namespace.

A name of the standard library is an identity that the scan cannot prove: code outside the
repository can replace it before the module runs. So `boundary_types` counts such a name only under
the opt-in contract premise `standard_library_unchanged`, and the PASS reads "PASS under outside
code leaves the standard library unchanged" (AD-782). This covers the closed table of value types
and markers (`pathlib.Path`, `datetime`, `typing.Final`, ...), the decorators that the collector
models, and, since #1718, the collections and special forms that the shape reader reads by name
(`typing.List`, `collections.abc.Sequence`, `typing.Optional`, `typing.Union`, `typing.Literal`,
`typing.Annotated`). Without the premise each of these positions is UNKNOWN and the cause names the
premise. A builtin of the language (`list[int]`, `dict`, `int | None`) needs no premise. A name that a
file of the repository may change (an attribute store of that name, a computed store, a store through
`vars`, `__dict__`, `sys.modules` or `globals`, or code run from a text) stays UNKNOWN even under the
premise. Before #1718 the shape reader counted `typing.List` and the other named collections with no
premise, so a scanned `typing.List = Secret` gave a false PASS
(`tests/test_cli_boundary_stdlib_collections.py`).

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

A TypeScript, declaration or JavaScript file under the scan roots that the TSConfig does not
select (`files`, `include`, `exclude`, `allowJs`) is a coverage gap that names the file, so no
rule of the run can PASS. Emitted names (`a.js` beside `a.ts`) and files in the `outDir` or
`declarationDir` are gaps too: a name does not prove generated code. A package in an installed
directory beside a valid manifest is not a gap while only a `node_modules` search reaches it. Its
closure is read instead (AD-798, see the top of this page). Test sources that `exclude_test_sources`
removes are not gaps. The gap holds every rule of the run.
Narrow the scan roots to the source, or select the file in the TSConfig
([AD-488](architecture/decisions/ad-488-a-source-file-that-the-tsconfig-drops-is-a-coverage-gap.md)).

A `.vue`, `.svelte`, `.astro`, `.mdx` or `.es6` file is a gap too: the collector does not read
these forms, and the gap names the file and the form (#1528). So is an `.html`, `.htm` or `.svg`
file that can hold code (#1607): a `<script` element (also in a `<template>` or an SVG), an `on*`
event handler attribute, a `javascript:` URL, `srcdoc`, or a `data:` URL of a page or an SVG. The
check is lexical and over-matches on purpose: a page that only looks like code is a gap, and a
page with plain markup is not. A file outside the scan roots is not a gap.

These files give no gap in the core and in 4.0.1 (follow-up work):
- `exclude_test_sources = true` removes `test`/`tests`/`__tests__` directories and `*.test.*` and
  `*.spec.*` files by design (AD-313, opt-in), also when such a file imports another component.

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
the bundler's aliases match tsconfig `paths`. The verdict states this assumption when
bundler mode is active; ArchKeel does not verify it. A
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
For Node, first check which declarations the project's locked compiler selects
(`tsc --noEmit --listFiles`). For example, `@types/node` can declare `process` even with
`lib: ["ES2022"]`. That is type evidence, not a runtime publisher.
If the deployment supplies Node's `process`, a reviewed `declare var process: NodeJS.Process;`
in a script `.d.ts` selected by both tools states that host contract. Check it with
`tsc --noEmit --skipLibCheck false` and check the binding under the actual startup options.
A preload can replace it. Without this contract, keep UNKNOWN or import the value from
`node:process` when the code needs that builtin specifically
([AD-870](architecture/decisions/ad-870-a-node-host-declaration-is-a-premise-not-a-runtime-publisher.md)).
Without `lib`, the target's default file applies, DOM included. Only top-level value declarations count, so types such as `Document` are not
proved, and a newer `lib` name waits for the pinned TypeScript version to move.
A `/// <reference types="./x" />` directive with a relative or absolute path names a file of the
project; it is UNKNOWN, as `path` and `lib` directives are (#976). A leading `types` name is a type-only edge to the package that the resolver proves in
`node_modules` (`@types/<name>` first, then the package); any other result, such as a package that
is not installed, a `typeRoots` setting, a candidate with `typesVersions` and a `types` field that
names a missing file, is UNKNOWN. A directive after code and `no-default-lib="true"` are not honored and
stay silent
([AD-528](architecture/decisions/ad-528-a-leading-types-directive-is-a-type-only-edge-to-its-package.md), #686).
A `declare module "x"` augmentation names a module as an import does: a relative or
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
Open false PASS, not accepted (AD-460, AD-508): any alias of `location` or `open` (a navigation
through an alias); a computed key
in a pattern (`const { [k]: v } = e`); any global that navigates or opens (`open('', '_self')`,
`document.open`); a destructured or aliased `setTimeout`; and DOM code from text outside the named
triggers (a `src` or `href` that is no literal, and a click on the element).
AD-766 (#1524) closes the window values of a host: a write with a run-time key into a value that
the file does not make (an event target, the `this` of a listener, an alias of `this`, `super.valueOf()`,
a parameter, a call result or a member) is an amplifier form, and so is `Object.assign`,
`Object.defineProperty(ies)`, `Object.setPrototypeOf`, `Reflect.set`, `Reflect.defineProperty` or
`Reflect.setPrototypeOf` on such a value (direct on a window value). With a host entry they block
every global proof. A new value, `Object.create(…)`, a local name bound once to a new value and the
`this` of a constructor keep the proof. The same holds for a reflective member that is read through
a window name (`globalThis.Object.assign`) and for `__defineGetter__` or `__defineSetter__` of any
object. A reflective member or an accessor member used as a value (stored, passed, called through
`call` or `apply`, `Reflect.apply(Reflect.set, …)`) is direct. Plants:
`native/typescript/src/script_window_value_tests.rs`, `tests/test_collector_false_pass_ts_window_values.py`.
AD-508 closed these forms: a write with a run-time key through `this` of a class method, through
`super` or through a name bound once to such a `this`; a call, `new`, tagged template, `call`,
`apply` or `bind` of a member with a run-time key (also through a comma, a condition, a logical
operator or `await`) on any value but `Math`, `JSON`, `Atomics`, `Intl` and `console` (a local
object literal is no exception: the data exemption failed its proof and is removed, AD-508); a reflection with a
run-time key (`getOwnPropertyDescriptor(s)`, `Reflect.get`, also stored or passed); a navigation with a
value that is no literal (`location.*`, `location = x`, a pattern or `for…of` target, `open(x, …)` with
any target); a free `Object`, `Reflect`, `location` or `open` that is passed, stored or returned; and a
destructuring pattern that takes a window member out of a value.
AD-760 (#1547, #1525) closes the looked-up value: a member read with a run-time key
whose value a call can reach after the read is the same direct form as the key call. The check
follows the value through a wrapper, a local name (also one that a later assignment writes), an
array or object literal that holds it, and the members `call`, `apply` and `bind`. A use that
leaves this walk (an argument, `Reflect.apply`, `Function.prototype.call.call`, a `return`, a write
to a member, an export, a class field, a default value, a local name in a script file) is the direct
form too, so `return map[key]` keeps every free standard name from a proof. A use that cannot call
the value keeps the proof: `typeof`, a comparison, a condition, arithmetic, a text, a loop over its
elements, a member with another plain name, and a pattern of plain names. Plants:
`native/typescript/src/script_lookup_tests.rs`, `tests/test_collector_false_pass_ts_lookup.py`.
AD-768 (#1527) reads a value that may be a prototype of the global object like a window value:
`X.prototype` of a name that is no class of the file, `x.__proto__` and a `getPrototypeOf` call.
Its escape (`g(EventTarget.prototype)`) and a write through it with a run-time key are direct
forms; a write of `__proto__` on a value that is not proven local is an amplifier form. A read of a
member (`Object.prototype.hasOwnProperty.call`), an element and a comparison keep the proof.
A reflective write on the prototype of a class of the file stays a false UNKNOWN in a scan with a
host entry. Plants: `tests/test_cli_native_prototype_patch.py`.
AD-792 (#1526) reads DOM code from a text: a member `write`, `writeln` or `open` of a document used
in any way but the direct call `document.write(…)` (`document.open()`, `call`, `bind`, a literal key)
is a direct form; a document (`document`, `ownerDocument`, `contentDocument`) that is passed, stored
or returned or taken by a pattern is an amplifier form; a write of `href`, `src`, `action`,
`formAction`, `data` or `baseVal`, or `setAttribute` of such an attribute, with a value that is no
literal is an amplifier form; `execCommand('insertHTML', …)` with markup that is no inert literal is a
direct form. An address that a framework renders from data (`<a href={url}>`) is covered by the
printed assumption of AD-810 (#1662): such addresses hold no `javascript:` code. A string or template
of the scanned sources, or a JSON or YAML file below a scan root, whose text holds `javascript:`,
`vbscript:` or `data:text/html` (any letter case, also with a tab or line end inside) withholds
every global proof, and the gap names the place.
Plants: `tests/test_cli_native_dom_code.py`.
Older classes stay open too: a use through `opener` or `document.defaultView`.
AD-788 (#1546, #1674) states the premise of every TypeScript verdict as "code outside the scan
roots hands in no global or platform object and replaces no global"; AD-810 (#1662) adds "and
addresses that a framework renders from data hold no javascript: code" (text header, JSON `premise`,
report). Every JavaScript, TypeScript or HTML file of the repository outside the scan roots is read
with the write detector of the scan (#1712): an alias of a window name, a window name passed to a
function, a destructuring or `for` target, `Reflect.apply(Reflect.set, …)`, `eval` and `Function`
texts withhold the proof as they do inside the scan (a form whose name the detector cannot read
withholds every global). A second reader names `window.x =`, `globalThis.x =`, `self.x =`, an
assignment to an undeclared name, a top-level binding of a classic script and the reflective writes
on a window name. A member patch of a global (`Math.max = f`,
`JSON.parse = f`, `console.log = f`, `Object.assign(Math, …)`, `console.__defineGetter__(…)`) with
a value that is no literal withholds the proof of each use of the patched member (and of the global
as a whole value), in such a file and in a scanned file ("Script global Math is patched by a member
write"); a use of another member (`Math.min`) keeps it. Each hit withholds the native proof of its name, and the
gap cites the use and the write. A write whose name the guard cannot read withholds every global.
There is no file limit (50 000 small files outside the roots add about 6 s). A file that the guard
cannot read (over the size limit of a file or the input limit of a scan) withholds every global,
and the gap names the file and what to do. Not read: test files (the test-source rule),
declarations, version-control metadata (`.git`, `.hg`, `.svn`), Python environments and tool
caches (`.venv`, `.tox`, `.mypy_cache`, `.pytest_cache`, `.ruff_cache`) and installed packages
(`node_modules`, `jspm_packages`, `bower_components`). Their code is third-party code outside the
scan roots, which the premise covers. Every other hidden folder (`.storybook`, `.vitepress`,
`.config`) is read. A stated generated copy of scanned sources (`// Generated from S;
source-sha256=H`, `// Owner: G`, `// Check: C`, with S a scanned file of digest H) is not read; the
premise then says that such a copy is the code of its sources. Test data in a folder `fixtures` is
read: the test-file rule names only `test`, `tests`, `__tests__`, `*.test.*` and `*.spec.*`. Code
outside the repository stays under the premise only.
A source file inside the roots that TSConfig `exclude` drops gives a named coverage gap (AD-488),
including a file that writes a global. It is no longer a silent false PASS.
A member `source`, `view`, `currentTarget` or a window name is a window, and a member `eval` or
`Function` is the global, on every object
([AD-492](architecture/decisions/ad-492-the-browser-assets-are-pinned-until-their-html-sinks-are-rewritten.md)).
An exemption for data that the file makes is follow-up work: a literal can carry an event or a prototype.
A markup literal is text only when it holds no handler, code element, URL attribute, style, code
scheme, `&` or `\\`.
AD-582 removed the former browser and Studio assets. The local Explorer now has its own assets.
The native TypeScript collector reads a file up to 4 MiB. Above that size it gives UNKNOWN for
the file, where the Python collector reads the file and can give FAIL. The two collectors give
the same facts only for files under the limit.

## Rust profile

A registry or git dependency named like a crate of the workspace is a pair gap from the module of
each reference to the module that the path reaches in that crate (AD-704): a redirect in or outside
the repository (`$CARGO_HOME/config.toml`, the `CARGO_*` environment, `--config`, a patch) or a
`git` URL of this repository can make it that crate. The pair is UNKNOWN until the contract allows
it, also where a patch in the repository makes the edge certain.

The native Rust collector reads the crate edges: a `use` path or a qualified path whose first
segment names another crate, and the module edges inside a crate: a path that starts at `crate`,
`self`, `super`, a child `mod`, a `use` binding or a glob `use` and names another module. A path
into another crate of the workspace names its deepest module. The collector also reads the
definitions of each module (symbols, AD-351). Calls, types and constructs are unsupported, so they
stay UNKNOWN and never PASS. The linked collector names the item of each import and its
publication route, so the core decides `interface_boundary` and symbol selectors
([AD-604](architecture/decisions/ad-604-the-rust-collector-states-the-item-and-route-of-each-import.md)).
A name that a `macro_rules!` call defines ends its route when the expansion writes no import at item
level ([AD-608](architecture/decisions/ad-608-a-crate-root-is-the-one-public-path-of-each-name-it-publishes.md)).
A glob into another component, a name that a macro may publish further (unless a hop of its route
is public), a method call whose receiver the scan does not know and a procedural macro are not
read: they hold the rule. A procedural macro that adds a `use` of a defined name can only give a
FAIL where the truth is PASS. A run through the subprocess reply states no interface. A name that a
file declares more than once and that may name a module, a glob that the scan cannot follow, a
`use` path that starts with a name that a glob may bring in, a `super` above the crate root, two
`macro_rules!` of one name and a path in a `macro_rules!` body that is relative to the place of the
call are UNKNOWN, and so is a macro call that the scan cannot place (in the tokens of another macro, or by the path of a module). A `crate::` path in a macro body is an edge of each call (AD-349). Edition 2015 (or none named
in the manifest): a `use` path and a `::` path start at the crate root. A method of an `impl` block
in another module than its type is an edge when a path names it (`impl crate::c::S { fn m() }` in
`b` and `crate::c::S::m()` in `a`: `a -> b`), when the type is exact and the member and its block
have no `cfg` or other attribute; else the path gives a gap of the pair (#1276). A derive keeps a
type exact only when `derive` is the macro of the prelude (`use m::rewrite as derive;` makes it an
attribute macro). A method call `x.m(..)` that may reach such a method
(it has `self`, the same number of other arguments, and a visibility that holds the caller), and a
call of a method of a trait that a glob brings in (`use b::T;` in the parent, `use super::*;` and
`5u8.m()` in the child), give a gap of the pair `a -> b`. A call on a plain `self` in a method of `impl S`, or a path `Self::m`, is an edge to the module of the one inherent member `m` of `S` and gives no gap when that member has the same `self` form (`self`, `&self`, `&mut self`) and no `cfg` or other attribute can change the member, its block, its module, the type or the caller; any other case keeps the gaps (AD-383). A `cfg_attr` that can add only lint attributes does not change an item (AD-535). A call `x.m()` on a parameter `x: T`, `&T` or `&mut T` is the same edge when `x` is bound once in the `fn`, `T` is a written plain path to one exact struct or enum, and the member has the `self` form of the parameter; a rebinding, a generic or `impl Trait` or `dyn` type, an alias, a mismatched `self` form, a `Deref` impl of the type and a macro that names `x` keep the gaps (AD-524). The host drops that gap only when the
contract lets `a` use `b` and the edge closes no cycle that the edges and the other pair gaps may
close (AD-357). A trait `impl` that is anchored in no module (neither its self type, read after `&`, nor its trait
is defined there; a trait argument never anchors; a block name anchors only without a `use`, an inline
`mod` or a second item of that name) gives a pair gap from each module of its crate and of each crate
that depends on it (AD-516). The price: one orphan in a crate of N modules gives N-1 gaps, and
`REQUIRES`, `NO-CYCLES` and the pair rule are UNKNOWN until the contract allows each pair; with one
component for each module the gap `c -> b` stays when `c` holds the type, because `b -> c` closes a
cycle. AD-806 (#1515, #1516): a module whose file holds a trait impl that runs code (a written block
with an item other than an associated type, or a derive other than `Copy`) gets a pair gap from each
module of its crate and of each dependent crate that reaches it over the edges and the pair gaps. This
covers a value of a type of `b` that the caller gets from another module (a method call, `Display`,
`Debug` through a format macro, `Drop`, `==`, `+`, `[]`, `*` through `Deref`, `for`, `?`, `into()`,
`impl Trait`, `dyn`, a field, an alias with `Default`, a closure), a trait of `b` reached through a
generic bound, a supertrait, a `dyn` supertrait or a re-export, and a foreign trait that a glob brings
in. A generic or `dyn` callee that runs an impl which its caller hands in gets no gap: the dependency
is the caller's, which reaches `b`. On `native/`, `NATIVE-NO-CORE-TO-RUST` and
`NATIVE-NO-CORE-TO-TYPESCRIPT` are UNKNOWN for this reason, because `core` reaches both collectors
through `collect`.
A member that a `macro_rules!` impl adds outside the file of its type gives a pair gap (AD-656); only
a type of the same arm, or an item of the module that every configuration has, anchors it (AD-662). A
call of a macro whose expansion the scan does not read (a procedural macro, a `macro_rules!` of a
crate outside the scan, a macro that an import binds) gives a gap of its module with an unseen
target, and each module that may reach an impl in the module of the call gets a pair gap (AD-662).
A `std` macro by its prelude name or a `std`, `core` or `alloc` path, and the registry macros
`serde_json` 1.0.154 `json!` and `schemars` 1.2.3 `json_schema!` with a proved identity, are read
through their tokens.
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
Path/git sources, workspace members and stale locks withhold this proof. Renamed registry
dependencies are followed through the manifest. AD-774 (#1518): each `.cargo/config.toml` and
`.cargo/config` at any level of the repository (not below build output, `.git` or `node_modules`) is
read. A replacement of the crates.io source or a `paths` override withholds the proof of every
registry crate; a `[patch]` entry of a configuration or a manifest, and a `[replace]` entry of a
manifest, withhold the crate that they name. A configuration that does not parse, a `.cargo` link,
an unreadable directory, a directory link, and a walk beyond depth 128 or one million entries
withhold every crate. A derive that loses its proof this way is UNKNOWN, and a gap names the file and
line of the setting. A configuration without such a setting (`[build]`, `[alias]`) keeps the proof.
Settings outside the repository (`$CARGO_HOME`, `CARGO_*` variables, `--config`) are not read, so a
result does not depend on the machine. A Rust scan whose proof rests on a locked registry crate
states the premise "the Rust code compiles (rustc accepts it); registry crates are built from the
identity that Cargo.lock records; no outside source replacement" with its verdict; a build that breaks it is outside the PASS.
`tests/test_collector_false_pass_rust_registry_replacement.py` holds the plants: the replacement in
the repository gives UNKNOWN, the same replacement in `$CARGO_HOME` gives PASS under the premise.
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

Explorer resolves direct calls between unconditional module functions in the
same crate target, including proven relative module paths. It can also
resolve a plain call on `self` when both methods share a proven inherent
implementation. Calls through local values, trait dispatch, general receiver
inference, and unread macro expansions stay unresolved. This is a partial
inventory
([AD-1033](architecture/decisions/ad-1033-prove-relative-rust-paths-and-inherent-self-calls.md)).

- **Definitions** ([AD-351](architecture/decisions/ad-351-the-rust-collector-reports-definitions-and-never-invents-one.md)).
  A public module-level item that a module-level call of a `macro_rules!` of the workspace writes
  is listed, from the transcriber or from the call tokens (AD-718); one whose name or visibility the
  call gives through a metavariable is listed with its kind and place but an unread name, so
  `unused_public` is UNKNOWN for it. The items of an `extern` block are listed. An item that syn
  cannot parse is a gap. An item of a procedural or foreign macro keeps the AD-662 gap. A method of an
  `impl` block is listed only when its type is a definition of the same module, so `impl Builder`
  in another module than `Builder`, an `impl` of a foreign type and an `impl` of a type that a macro
  generates give no method. A gap would make the whole scan incomplete, so the report says
  `partial` for the symbols of each module and for the methods of each type. A field, an
  associated type and the visibility of a `mod` are not read. A definition under a `cfg` that the
  scan does not know is read (the union of the cases).
- **`extern crate` without a manifest entry.** `extern crate base_crate;` with no entry in
  `Cargo.toml` is UNKNOWN, never PASS. It compiles only when a `build.rs` prints
  `cargo:rustc-link-search=crate=...`. Such a link is not read
  ([AD-356](architecture/decisions/ad-356-a-call-or-crate-that-a-producer-cannot-see-is-a-gap.md)).
- **`extern crate self as name;`** binds `name` to the root of the own crate. In the crate root it
  joins the extern prelude: `name::b::g`, `use name::b::g;` and `::name::b::g` in any module of
  that crate are an edge to `b`, and so is `crate::name::b::g` where a module binds the alias. An
  alias in a function body is read in its own file only. A file that declares the name itself, or a
  glob that may bring it in, makes the path UNKNOWN. Not seen, and the verdict can be PASS: the
  alias through a `pub use` of the root (`pub use crate::name as other;`), the same class as any
  other path through a re-export of the root. An alias that a macro generates is a macro
  expansion gap. An alias item with a `cfg` or `cfg_attr` is a gap, also when the condition is
  always true.
- **A glob import.** A glob is read only when the resolver of `use` paths takes its whole path to
  a module of the crate that has no module-level macro call, or to an external crate. Any other
  glob that may bring in the first name of a path makes that path UNKNOWN.
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

The baseline codec reads schemas 1.0.0 through 1.4.0 ([AD-386](architecture/decisions/ad-386-the-contract-crate-reads-and-writes-baselines.md), [AD-546](architecture/decisions/ad-546-a-baseline-accepts-an-unknown-by-what-it-is-and-the-core-compares-it-both-ways.md)). It writes 1.4.0 for a run and 1.3.0 for a file that has no `unknowns` list. It keeps every entry and the permissive Python string rules. It refuses repeated JSON keys, lone surrogates, numbers outside its integer range, nesting deeper than 128 and files over 16 MiB. `validate --baseline` and `--write-baseline` use it. The core measures only `cycle_edges` and `private_crossings`. The three call and typing budgets are `budget.unmeasured` until slice D. The HTML report does not mark accepted entries. A TypeScript parser gap and a Dart file gap give their position in the reason, and the key drops a trailing `at line N` or `:N` by the text.

The API list of `tools/rust_api.py` expands the `macro_rules!` calls of a crate before it counts
(`tools/rust_macros.py`, [#1048](https://github.com/rapiddweller/archkeel/issues/1048)). A call that
it cannot expand, an exported macro and a name with two definitions are lines `unexpanded` in
`native/api_baseline.json`. A macro of another crate, of the standard library, and a proc macro
(attribute or derive) are not expanded. A call by a path is expanded when the path starts at `crate`,
`self`, `super` or a module of the crate; a path through an alias or an extern crate with a name that
a local macro has is a line `unexpanded`. A macro that a macro call defines serves the later calls of
the same file only; a transcribed `$name` that the call does not bind (a variable of the inner
definition) is a line `unexpanded`. A call under `#[cfg(...)]` counts as if the configuration were on,
like any other item of the list. Two `pub fn` of the same name in two `impl` blocks of one
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
- A method call can reach a member in another crate through any crate of the Cargo closure of the caller, and the collector lists such candidates. A method in the file of its type, called on a value that the caller does not name (a field, a chain of fields, the return value of a function), is a candidate too: it gives a pair gap when the module of the type is reachable from the caller over the edges and the pair gaps, or when the caller reaches a module with a gap that names no target (#1571); a path `T::m` reaches it only when `T` is the name of the type, an alias or a renamed `use`, or a macro of the caller can give any name. When the written types prove the receiver type ([AD-804](architecture/decisions/ad-804-a-written-receiver-type-narrows-a-rust-method-call.md)), a std type gives no candidate and an exact own type gives only its own members; a std method of a later lookup step counts only in a file where no trait of another crate can be in scope. A trait method whose impl is in the module of its trait or of its type gives the pair gap of AD-806 to each module that reaches that module (an impl in a third module gives a pair gap, AD-516).
- A PASS beyond Python is only as strong as the edge model of the collector. The open false-PASS class #1004 (a value of a type that an anchored impl serves, when the caller does not name its module) gives no edge and no gap; an item that a macro makes gives a gap since AD-662. Where Python gives UNKNOWN only for a kept gap, the Python UNKNOWN hid them; the core PASS does not ([AD-418](architecture/decisions/ad-418-a-dropped-pair-gap-holds-the-rules-it-can-change-and-a-scoped-requires-needs-its-runtime.md)).

The dual-run request is a test protocol that only test builds and the cargo feature `harness` have (#1095); a release binary refuses it. Its `collector_argv`, `pinned` and `standard_library` fields are the word of the caller, not evidence: a wrong producer or an extra standard library name can give a PASS that Python does not give. The request of M1 must not take them from a caller: the shell starts the pinned collector, checks its digest and fills the producer and the standard library from its own profile table.

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
