# AD-450 Python import rules use a bound import survey

**Status.** Proposed. Part of #880. It extends AD-334, AD-388, AD-406 and AD-426.

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
   - A call of `__import__`, `import_module`, `load_module`, `exec_module`, `module_from_spec`,
     `spec_from_file_location`, `run_module`, `run_path`, `exec` or `eval`: a dynamic import.
   - A write to `sys.path` or a call of `site.addsitedir`.
   - An import of a project name that has no selected module, as a namespace package.
   - A star import of a project module: `__all__` can import submodules.
   - `from pkg import name` when the module `pkg.name` exists and `pkg` binds `name`, or has
     `__getattr__` or a star import and does not import `pkg.name` itself. Either can be given.
   - A relative import above the top package.
   - A syntax error, a file that is not UTF-8, a file or directory that cannot be read (#1043).
     The repository survey of `collect` refuses a directory that it cannot list before this.
   - A `.pyi` file or a compiled module (`.so`, `.pyd`) below a scan root.
   - One module name in two files, also across scan roots (#1000).
8. An import under `if TYPE_CHECKING:` or another condition is an edge. The record keeps
   `under_type_checking`. A rule reads such an edge as it reads a TypeScript type-only import.
9. `ScopeComplete`, `Scope::complete`, `Scope::pass_run` and `ModelTree::pass_run` stay the
   only PASS makers. The model, the evaluator and the report name no language.

**Reason.** Python projects had no verdict on the core. The import rules need only the import
graph, the module files and the scan roots. Each case that can hide an edge is a named gap.

**Rejected.** Running an interpreter for its standard library: the result depends on the host.
The union of the minor lists: a project on 3.12 can install `distutils` as a package.
A gap for each module only: a dynamic import can reach any module of the project.

**Limits.** The rules that read symbols, calls or constructs stay UNKNOWN (AD-426 limits).
#1072: the parser accepts some files that CPython refuses. Such a file adds edges, never removes one.
The core trusts the collector in its process for a complete file list (AD-406).
A namespace package that a test or another distribution extends is outside the scan roots.
A directly imported namespace package without `__init__.py` is UNKNOWN, not decided.
A file that changes during the scan refuses the run. This is not an atomic snapshot.

**Tests.** `tests/test_cli_native_python_imports.py` runs the release core and the default shell:
PASS, forbidden import FAIL with file and line, cycle FAIL and each named gap UNKNOWN.
`native/collect/src/python_tests.rs` plants digests. `native/store` tests plant each refused
claim. `native/python` tests cover each gap condition.
