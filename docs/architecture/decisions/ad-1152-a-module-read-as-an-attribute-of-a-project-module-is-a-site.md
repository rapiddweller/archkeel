# AD-1152 A module read as an attribute of a project module is a site

**Status.** Accepted. Issue #2079. It extends [AD-1098](ad-1098-a-module-that-holds-a-hazard-name-is-a-site-when-it-flows-as-a-value.md) and [AD-1094](ad-1094-a-project-module-that-re-exports-a-standard-library-module-hands-on-its-trojan-horse.md).

**Reason.** `app.util` holds `import cProfile as cp`. CPython 3.12 imports `app.lib` in each form below, and `forbidden_dependency` gave PASS with no gap, because the survey read `util.cp` only as the base of a longer chain.

- `getattr(util, 'cp').run(...)` and `m = getattr(util, 'cp')`
- `cp = util.cp`, `{'m': util.cp}`, `h.m = util.cp`
- `vars(util)['cp']` and `util.__dict__['cp']`
- `mid` holds `from app.util import cp as q2`; the consumer reads `q2.run` or `mid.q2.run`.

**Decision.** The first read of the value is the site; there is no flow analysis.
1. An attribute read (Load) whose name is a re-exported name is a site, unless a call or a longer chain reads it further (`util.cp.run` has its own rule; `pickletools.dis(x)` is a call).
2. A literal key that is a re-exported name is a site in `getattr(x, 'cp')`, `vars(x)['cp']` and `x.__dict__['cp']`.
3. A rename of a re-exported name is re-exported too: the table adds each name whose origin ends in a name of the table (`from app.util import cp as q2`), over two passes.

**Narrowing.** None. The change only adds sites.

**Limit (precision).** The rules are keyed on the name, as AD-1094 is. A read of an unrelated attribute with a name of the table (`self.logging`, `cfg.profile`) is a site while a module of the scan imports that module. A rename chain of more than two hops is not followed.

**Tests.** `tests/test_collector_false_pass_python_module_attribute.py`: 9 plants (CPython 3.12 imports `app.lib`; the verdict must be UNKNOWN or FAIL) and 6 controls that stay PASS. The mutation that removes the three rules fails all 9 plants.
