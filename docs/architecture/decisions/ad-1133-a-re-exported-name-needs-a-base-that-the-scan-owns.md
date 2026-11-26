# AD-1133 A re-exported name needs a base that the scan owns

**Status.** Accepted. Issue #2048. It narrows [AD-1094](ad-1094-a-project-module-that-re-exports-a-standard-library-module-hands-on-its-trojan-horse.md).

**Reason.** The re-export table of AD-1094 is keyed on bare names: any module of the scan that imports `types` adds the key `types`. The attribute `pa.types` (`pa` is `pyarrow`) then met that key and gave a `dynamic_import` site named `types`. In DATAMIMIC EE, `parquet_reader.py:115` (`types = pa.types`) turned 199 rules from PASS to UNKNOWN. The value is an attribute of a third-party module, not the standard library module `types`.

**Decision.** A chain `base.name.rest` reads the re-export table only when the base is not an import of a module outside the scan. A base that an import binds is judged by its origin: the table applies when the top package of an origin is a package of the scan (`app.util`). A base with no import (a parameter, a call result, a relative import) keeps the table, because its value is unknown.

**Rejected.** Keys with the qualified name of the owning module. A relative import (`from . import util`) has no binding in `bindings`, so a qualified key would lose a real route.

**Limit (precision).** A parameter or a local value that is no import (`def f(x): x.types`) still reads the table. It gives a site while another module imports `types`. That is UNKNOWN where PASS may be right; the value of a parameter is unknown to the scan.

**Tests.** `tests/test_collector_false_pass_python_value_binding.py`: 5 controls stay PASS, among them the shape of `parquet_reader.py` with a second module that imports `types`; 4 plants (CPython 3.12 imports `app.lib`) stay UNKNOWN, among them the relative import. The mutation that removes the check fails 2 controls.
