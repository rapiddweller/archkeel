# AD-1146 An outside file holds symbol records only for a use that can write

**Status.** Accepted. Part of #1963 and #1919. It narrows [AD-770](ad-770-code-of-the-repository-outside-the-scan-that-writes-a-module-of-the-scan-withholds-its-routes.md) and extends [AD-1118](ad-1118-a-file-outside-the-scan-that-withholds-symbols-is-named-by-a-symbols-gap.md).

**Reason.** One site that is not proven harmless made every string of the outside file name modules, so the survey withheld the symbol records of each of them. On CE, `script/check_installed_authoring.py` has eight such sites: three `import importlib.*` lines, one walk over `sys.modules`, two `importlib.util.find_spec(...) is None`, `importlib.metadata.version(...)` and `importlib.resources.files(...)`. None of them writes a binding. They held 540 modules: 0 of 16,391 calls resolved, 798 `interface.usage_unknown`.

**Decision.** A site is harmless when the whole file uses the name only to read:
1. `importlib`: each chain is one of `importlib.metadata.version` (a text), `importlib.metadata.PackageNotFoundError`, `importlib.resources.files`, or `importlib.util.find_spec`. The use of the result decides, not the call:
   - `find_spec(...)` is a read only when it is tested with `is None` or `is not None`.
   - `files(...)` is a read only when its result is the start of a path read: `.read_text()`, `.read_bytes()`, `.is_file()`, `.is_dir()` or `.exists()`, directly or after `.joinpath(...)` or `/ name`. A name that binds the result must be stored once, and each load of it must start such a read. A write (`.write_text`, `.write_bytes`), `.open`, `.iterdir`, a pass to a function or any other use keeps the hold.
   - Any other chain, a bare name, an alias (`import importlib.x as y`) or a `from importlib import` ends the proof.
2. `sys.modules`: each use is a test `name in sys.modules` as the last operand of the comparison as the last operand of the comparison or the iterable of a `for` or a comprehension. A subscript, `.get`, `.values`, an assignment to a name, `sys.__dict__`, `vars(sys)`, an alias or `from sys import` ends the proof. Other attributes of `sys` must be one of `argv`, `base_prefix`, `executable`, `exit`, `flags`, `flags.isolated`, `path`, `platform`, `prefix`, `stderr`, `stdout`, `version_info`.
3. A name that stands for `sys` or `importlib` and is bound to anything else ends the proof for it: an assignment, a loop or `with` target, a parameter, an `except ... as`, a pattern, a `def`, a `class`, or `import x as sys` (Codex #2099: `sys = Replacement()` ran a hook at `x in sys.modules`).
4. The proof is for the whole file, so a write elsewhere in the file keeps the hold for all its sites.

**Why this is sound.** None of these uses gives a module object or a writable handle, so none can write a module attribute, a class or a `sys.modules` entry, or change the file of a module. `find_spec`, `files` and `version` can import a package; the import runs code that the scan reads and changes no binding. A first version judged only the call of `files(...)`: `files('app').joinpath('service.py').write_text(...)` rewrote a scanned file and the rule passed (found by the verification run of #2072). The use of the result is now judged.

**Can it enable a PASS?** Yes: a module that was withheld is now read. The counter-examples that I ran keep the hold, and each is run with Python to show that the scanned code changes: a subscript write, a replaced module, `.get` then write, a write through an imported module, `sys.__dict__`, `vars(sys)`, a namespace in a name, a walk then a subscript. A membership chain `x in sys.modules in sink` keeps it too (Codex #2072). A membership chain `x in sys.modules in sink` keeps it too (Codex #2072). Four more keep the hold with no effect shown: `entry_points`, a used spec, an alias, `sys.modules.values()`, `files(...)` passed to a function, `files(...).iterdir()`. Mutations: both proofs true fail 7 of the first 9 plants; a `files` call that is always a read fails the four `files` plants.

**Rejected.**
- A list of harmless call names without the file-wide proof: one `sys.modules[...]` write in the same file would pass.
- A proof for each site: the hold of one site names every string of the file, so the file is the unit.

**Limit.** An alias or `from importlib import metadata` keeps the hold. A use through `gc`, a frame or a C extension is outside the stated premise.

**Tests.** `tests/test_cli_python_outside_reads.py`.
