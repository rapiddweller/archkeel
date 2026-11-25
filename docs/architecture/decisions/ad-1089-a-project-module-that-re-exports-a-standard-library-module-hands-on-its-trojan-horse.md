# AD-1089 A project module that re-exports a standard library module hands on its trojan horse

**Status.** Accepted. Issue #1973. It extends [AD-1059](ad-1059-a-standard-library-name-that-imports-by-a-string-is-a-trojan-horse.md) and [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md).

**Reason.** `util.py` holds `import cProfile`. `consumer.py` calls `util.cProfile.run('import app.lib')`. CPython 3.12 imports `app.lib`, and `forbidden_dependency` gave PASS with no gap. The survey resolved a name only through the import bindings of the module that uses it. The same hole existed for `unittest.mock.patch`, `dis.Bytecode`, `unittest.main`, `unittest.TestLoader` and `trace.Trace`. A false PASS is the worst defect.

**Decision.**
1. The survey builds one table for the scan. It maps each name that an import statement of any module binds to the qualified origin of that name. It keeps an origin only when the origin is a module above a hazard name and no hazard itself (`cProfile`, `unittest.mock`, `logging`, `sys`). The import of a hazard (`import pickle`) is a site already.
2. In each attribute chain, an attribute that is a key of the table starts a new read. The rest of the chain is read from each origin of that key with the rules of AD-450 and AD-1059. A hit is a site with the name of the origin (`cProfile.run`, `unittest.mock.patch`). The gap is `dynamic_import`, as for the other trojan horse names.
3. The rule applies to each base: a project module, a call, a local or a parameter. It runs after the existing checks, so a chain that was a site before keeps its detail.
4. `import cProfile as cp` in `util` binds `cp`: `util.cp.run` is a site too.

**Rejected.**
- A site for each attribute of a project module that re-exports: it refuses `util.json.dumps` and `util.os.path.join`.
- A rule that follows the import graph from `consumer` to `util`: the chain can start at any value, and the table is simpler.

**Limit (precision).** The table is global. A module that binds `config` to `logging.config` makes `x.config.dictConfig` a site in every module. An unrelated attribute with the name of a re-exported module, such as `self.mock.patch`, is a site too. No rule gives PASS where it gave UNKNOWN before.

**Premise.** A module that a parameter hands in (`def helper(m): m.config.dictConfig(...)`) needs the module in the scan, and the import of `logging.config` there is a site already. The form `getattr(util, 'cProfile').run(...)` is not read (#1979 keeps `__call__` open).

**Tests.** `tests/test_collector_false_pass_python_reexport.py` (CPython 3.12 imports `app.lib` in each plant; the verdict must be UNKNOWN or FAIL; each control stays PASS) and the unit test in `hazards_reexport.rs`. The mutation that makes `find` return `None` fails nine of eleven plants.
