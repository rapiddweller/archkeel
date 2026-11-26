# AD-1133 A re-exported name needs a base that the scan owns

**Status.** Accepted. Issue #2048. It narrows [AD-1094](ad-1094-a-project-module-that-re-exports-a-standard-library-module-hands-on-its-trojan-horse.md).

**Reason.** The re-export table of AD-1094 is keyed on bare names: any module of the scan that imports `types` adds the key `types`. The attribute `pa.types` (`pa` is `pyarrow`) then met that key and gave a `dynamic_import` site named `types`. In DATAMIMIC EE, `parquet_reader.py:115` (`types = pa.types`) turned 199 rules from PASS to UNKNOWN. The value is an attribute of a third-party module, not the standard library module `types`.

**Decision.** A chain `base.name.rest` reads the re-export table only when the base is not an import of a module outside the scan. A base is proved only when one module-level binder binds its name (`Binders::unique`) and that binder is an import. Then the origin judges it: the table applies when the top package of the origin is a package of the scan (`app.util`). Any other base keeps the table: a parameter, a call result, a relative import, a name that an unrelated function also binds (`import json as m` in another function does not prove the parameter `m`).

**Rejected.** Keys with the qualified name of the owning module. A relative import (`from . import util`) has no binding in `bindings`, so a qualified key would lose a real route.

**Limit (precision).** A parameter or a function-level import (`def f(pa): pa.types`, `pa` imported inside another function) still reads the table. It gives a site while another module imports `types`. This is the shape of `parquet_reader.py:115` in DATAMIMIC EE: the scan cannot prove that the parameter is `pyarrow`. The owner declares the site (`declarations.trojan_horse_reach`) or the scan needs a flow proof of the argument.

**Tests.** `tests/test_collector_false_pass_python_value_binding.py`: 4 controls stay PASS (a module-level `import pyarrow as pa` while another module imports `types`); 5 plants (CPython 3.12 imports `app.lib`) stay UNKNOWN, among them the relative import and the parameter that an unrelated import in another function shares its name with (Codex finding, P1).
