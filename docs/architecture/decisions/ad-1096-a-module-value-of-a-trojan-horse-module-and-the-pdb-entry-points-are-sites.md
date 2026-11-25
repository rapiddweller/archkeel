# AD-1096 A module value of a module with trojan horse names, and the pdb entry points, are sites

**Status.** Accepted. Issue #1976 (cases 1 to 4). It extends [AD-1059](ad-1059-a-standard-library-name-that-imports-by-a-string-is-a-trojan-horse.md).

**Reason.** CPython 3.12 imports `app.lib` in each plant below, and `forbidden_dependency` gave PASS with no gap. The survey read a hazard name only through an import binding or a direct attribute chain.

**Decision.**
1. A literal import call (`importlib.import_module('unittest')`, `__import__('dis')`) whose module is a hazard, or holds a hazard name of AD-450 or AD-1059, is a `dynamic_import` site. The proven import edge stays.
2. `vars(m)` and `m.__dict__`, read with a literal key, are a site when `m` is a name that an import binds to such a module (`import dis`, `import dis as d`). Before, a literal key cleared the read.
3. The names `cProfile.main`, `profile.main`, `pdb.main` (they import the module that `sys.argv` names with `-m`), `pdb.set_trace`, `pdb.post_mortem` and `pdb.pm` (they read commands from the standard input) are importer names of AD-1059.

**Rejected.** A site for each literal key of each `__dict__`: `vars(args)['config']` is ordinary code.

**Limit (precision).** A literal import of `logging`, `unittest`, `xml.sax` or `dis` is a site. The standard input and `sys.argv` that a plant sets are outside the scan, so the entry points are sites by name. A `__dict__` of a name that is no import binding (an alias through a variable) is not read. The string annotations (case 5) are #1974.

**Tests.** `tests/test_collector_false_pass_python_module_routes.py` (CPython 3.12 imports `app.lib` in each plant; the verdict must be UNKNOWN or FAIL; four controls stay PASS). The mutation that removes the three rules fails 11 of 15 plants.
