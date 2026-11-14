# AD-450 Python import rules use a bound import survey

**Status.** Proposed. Part of #880. It extends AD-334, AD-388, AD-406 and AD-426. AD-472 narrows
the gaps of a direct literal import call and of a stub beside its source.

**Decision.**
1. `native/python` has a library. `archkeel-collect` links it and takes the typed reply.
   The binary reads stdin and writes bytes of the same survey. The store and model are unchanged paths.
2. The request is 10.0.0. The core runs no Python interpreter. The grammar is that of 3.14.
   A name is standard when each pinned list of 3.11 to 3.14 has it (AD-388). The core settings
   use the same list. A name of some minors only, such as `distutils`, is an external package.
3. A target is project, standard or external by its first part, as a bare TypeScript specifier.
   The namespace of the configuration is the project. Its target needs a selected module, else
   the survey writes a gap. A standard name is builtin. Each other name is an external package.
   The rules read a Python target by its module scope, as 4.0.1 does (`TargetMarks::ByModule`):
   the dependency `google.cloud` matches `google.cloud.storage`.
4. The survey binds itself. Each parsed file must have the input digest of its parsed bytes.
   `collect` reads each input again: each digest and the source digest must agree, else refusal.
5. The store accepts 10.0.0 only from the Python profile, and Python only in 10.0.0. It
   accepts only the sections `imports` and `unknowns`, no feature and no construct. The
   coverage gaps must be the `unknowns` section. A project target cannot be builtin or external.
   A builtin must be standard, and an external package must not be standard or a project name.
   The linked reply states that symbol selectors and interfaces are not supported (AD-426).
6. Layout: the file of a module must be its module path, and its top package directory must be
   a scan root or lie below one. Then the parent rule of `Layout::ProjectFiles` holds for
   Python, and the scan receipt can decide. Else a gap. A reply scope label is `<root>/**`.
7. Each case below is a named coverage gap. A gap makes the scope incomplete: every rule is UNKNOWN.
   - A reference to a standard-library door is a `dynamic_import`: a call, an alias, a value or an
     attribute of `__import__`, `exec`, `eval`, `compile`, `importlib` loaders, `pkgutil`, `pydoc`,
     `runpy`, `imp`, `zipimport`, `code`, `codeop`, `timeit`, `doctest`, `pickle`, `marshal`,
     `shelve`, `dill`, `cloudpickle`, `ctypes.pythonapi`, `types.FunctionType`/`CodeType` and
     `unittest.mock.patch` (`hazards.rs`). Names resolve through import aliases. `sys`,
     `importlib` or `builtins` used as a value (`getattr(sys, ...)`) is a door too.
   - A reference to `sys.path`, `sys.meta_path`, `sys.path_hooks`, `sys.path_importer_cache`,
     `sys.modules` or `site`, or a write to `__path__`, is an `import_system_change`.
   - A project name without a selected module, also through `from pkg import name` when `pkg/name/`
     is a directory without `__init__.py`.
   - A star import of a project module: `__all__` can import submodules.
   - `from pkg import name` when the module `pkg.name` exists and `pkg` binds `name`, or has
     `__getattr__` or a star import and does not import `pkg.name` itself. Either can be given.
   - A relative import above the top package. One module name in two files (#1000).
   - A syntax error, a file that is not UTF-8, an encoding declaration other than UTF-8 or ASCII
     (PEP 263), an unreadable file or directory (#1043), and a linked directory below a root.
   - A `.pyi` file, a `.pyw` file or a compiled module (`.so`, `.pyd`, `.pyc`) below a scan root.
   - A component that names a module outside the namespace (the reference engine refuses it).
8. An import in any branch is an edge. Only the body of `if <guard>:` is `under_type_checking`.
   The guard is a `TYPE_CHECKING` that only an import from `typing` or `typing_extensions` binds.
9. `ScopeComplete`, `Scope::complete`, `Scope::pass_run` and `ModelTree::pass_run` stay the
   only PASS makers. The model, the evaluator and the report name no language.

**Reason.** Python projects had no verdict on the core. The import rules need only the import
graph, the module files and the scan roots. Each case of point 7 is a named gap. A third-party
function that imports from a string stays open (docs/known-limits.md).

**Rejected.** Running an interpreter for its standard library: the result depends on the host.
The union of the minor lists: a project on 3.12 can install `distutils` as a package.
A gap for each module only: a dynamic import can reach any module of the project.

**Limits.** The rules that read symbols, calls or constructs stay UNKNOWN (AD-426 limits).
#1072: the parser accepts some files that CPython refuses. Such a file adds edges, never removes one.
The discovery walk of the collector in the core process makes the file list (AD-406); the repository
survey of `collect` lists the whole tree first and refuses what it cannot list. The store cannot see a missing file.
A namespace package that a test or another distribution extends is outside the scan roots.
A directly imported namespace package without `__init__.py` is UNKNOWN, not decided.
A file that changes during the scan refuses the run. This is not an atomic snapshot.

**Tests.** `tests/test_cli_native_python_imports.py` runs the release core and the default shell:
PASS, forbidden import FAIL with file and line, cycle FAIL and each named gap UNKNOWN.
`native/collect/src/python_tests.rs` plants digests. `native/store` tests plant each refused
claim. `native/python` tests cover each gap condition.
