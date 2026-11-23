# AD-1059 A standard library name that imports by a string or hands out a code object is a trojan horse

**Status.** Accepted (owner decision, 2026-11-23). It extends the list of trojan horse names of [AD-450](ad-450-python-import-rules-use-a-bound-import-survey.md), [AD-1053](ad-1053-a-computed-attribute-name-on-an-unproved-receiver-is-a-trojan-horse.md) and [AD-1058](ad-1058-receiver-annotation-and-exposure-proofs-of-the-trojan-horse-rules-are-tightened.md). It closes #1969 and #1970.

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** Python 3.12 imports a module that a string names in each plant below, and the rule `forbidden_dependency` gave PASS with no gap. A false PASS is the worst defect. A precision loss is fine.

**Decision.** The names below are trojan horse sites. The survey resolves each name through the import bindings of the module that uses it (`import logging.config as lc`, `from logging.config import dictConfig as dc`, `from logging import config`, a star import). A name that a function binds (a parameter or a local) is never matched. A name that nothing binds stands for itself. A project function, method or parameter named `dictConfig`, `loadTestsFromName` or `profile` is no site. The gap is `dynamic_import`, as for the other trojan horse names. No contract form exists for them, so no declaration applies (AD-664).

| Family | Names | How Python imports |
|---|---|---|
| Logging configuration (#1970) | the module `logging.config` (`dictConfig`, `fileConfig`, `listen`, `DictConfigurator`, `BaseConfigurator`) | the keys `'()'`, `'class'`, `'filters'`, `'handlers'`, `'formatters'` and `ext://` of a dictionary or file name a module |
| Test loader (#1970) | `unittest.TestLoader`, `unittest.defaultTestLoader` (also from `unittest.loader`), and with them `loadTestsFromName(s)` and `discover` | the loader imports the dotted name or the directory |
| Test program (#1970) | `unittest.main`, `unittest.TestProgram` | the parameters `module`, `defaultTest` and `argv` name modules |
| Code object (#1969) | `dis.Bytecode`, `dis.get_instructions`, `dis._get_code_object`, and the modules that re-export `dis`: `inspect.dis`, `modulefinder.dis`, `pdb.dis`, `trace.dis`, `sre_compile.dis` | `Bytecode(f).codeobj` and the `argval` of an instruction hand out a code object, so `type(f)(code.replace(co_names=...), {})` imports any module |
| Text run by a tool | `profile.run`, `profile.runctx`, `profile.Profile`, `cProfile.run`, `cProfile.runctx`, `cProfile.Profile`, `trace.Trace`, `bdb.Bdb`, `pdb.run`, `pdb.runeval`, `pdb.runctx`, `pdb.Pdb` | `exec` of the statement text |
| Builtin | `help` | `help('a.b')` imports `a.b` |
| Parser list | `xml.sax.make_parser`, `xml.sax._create_parser` | the list names parser modules |
| Private routes | `multiprocessing.spawn`, `warnings._setoption`, `warnings._getcategory`, `warnings._processoptions` | `runpy` of a module name; the category `a.b.C` |

**Two shape rules keep ordinary code clear.**
1. A call of `unittest.main`, `unittest.TestProgram` or `xml.sax.make_parser` is no site when it has no positional argument, no `**` and no keyword that carries a name (`module`, `defaultTest`, `argv`, `parser_list`): `unittest.main()` and `xml.sax.make_parser()` import nothing that the scan cannot see. `unittest.main()` reads test names from the command line, which is outside the scan (the premise of the run). The import `from unittest import main` and each other reference to the name stay sites, because a later call cannot show its arguments.
2. A module above one of these names is no site when it is a value (`getattr(logging, level)`, `logging.Handler.__init__(self)`). The list `TROJAN_HORSES` of AD-450 keeps this rule; the new list `IMPORTERS` does not have it. The first measurement with the rule (datamimic-ee) gave two new sites for these ordinary uses of `logging`. The access forms with a computed name that reach a child from a module value are sites already (AD-1053, AD-1058). A plain attribute is not: `def helper(m): m.config.dictConfig(...)` called with the `logging` module gives PASS (#1973).

**Star imports.** `from M import *` binds each name that `M` holds. A star import of a module that holds a hazard name directly is a site named `M.*`: `from logging.config import *`, `from dis import *`, `from unittest.mock import *`, and `from sys import *` (the state of the import system). A star import of a module that holds none (`from os.path import *`) is no site. `from logging import *` and `from unittest import *` are sites: precision loss, because `logging.config` and `unittest.main` are direct children.

**Precision loss.** The import of `logging.config`, `from unittest import main` and `from xml.sax import make_parser` are sites, also with no call. A module-level project function named `help` is a site, as one named `exec` is. A module-level variable named `profile` or `trace` with the attribute `run` or `Trace` is a site. A call of `dis.Bytecode` that only reads the opcode names is a site. No rule gives PASS where it gave UNKNOWN before.

**Premise.** The names are matched in the module that uses them. The scan reads no attribute of a project module that re-exports a standard library module (`util.dis.Bytecode` with `import dis` in `util`): this is open since AD-450 (#1973) and also holds for `unittest.mock.patch`. The module `logging.config` is not open: the import of it is a site. The command line and the environment (`PYTHONWARNINGS`, `PY_SAX_PARSER`, `PYTHONBREAKPOINT`) are outside the scan. A module, a loader or a Bytecode object that a parameter hands in is an unknown value (#1973) (`known-limits.md`).

**Not done.**
- `typing.get_type_hints`, `typing.ForwardRef` and other evaluation of a string annotation. CPython 3.12 imports a module when an annotation is `"__import__('app.lib')"`. The call is ordinary code (12 files of datamimic-ce), so a site would refuse it. Open as #1974, with a strict expected failure. Fix route: a site only for an annotation string that holds a call.
- Four routes found by the independent run (#1976, strict expected failures, old holes): the module value of a literal import call; `vars(dis)` and `dis.__dict__`; the `-m` entry points of `cProfile`, `profile` and `pdb`; `pdb.set_trace()` with a scripted stdin; and `eval_str=True`.
- `multiprocessing` spawn and fork servers (the child process imports, not the parent), `importlib.metadata.entry_points().load()` (needs an installed distribution) and `rlcompleter` (a CPython 3.12 plant did not import).
- `logging.config.listen` has no CPython plant in the tests (it needs a socket). It is in the list because `logging.config` is a whole module, and a run by hand showed the import.

**Measured.** datamimic-ee `560d5c7ef` and datamimic-ce `23bd48d9` (scan roots only): 125 and 70 collection gaps before and after, no new site, no rule changes. The fixture `K-python-realworld` (FastAPI RealWorld) goes from 1 to 3 gaps: its Alembic `env.py` has `from logging.config import fileConfig` and calls it with a file name. This is ordinary code, and a file can name a handler class, so it stays a site; the pin in `fixtures/matrix.json` is updated. The test directories of both projects use `unittest.main()` and `cProfile`; they are outside the scan roots.

**Tests.** `tests/test_collector_false_pass_python_stdlib_importers.py` with `tests/python_stdlib_importer_plants.py` (CPython 3.12 runs each plant and the test asserts that `app.lib` is loaded; each plant must be FAIL or UNKNOWN; each control stays PASS), `tests/test_collector_false_pass_python_open.py` (the open limits #1973, #1974 and #1976, strict expected failures), `hazards_importers_tests.rs`.
