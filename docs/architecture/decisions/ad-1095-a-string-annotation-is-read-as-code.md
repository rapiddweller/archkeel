# AD-1095 A string annotation is read as code

**Status.** Accepted. Issues #1974 and #1976 (case 5). It extends [AD-1059](ad-1059-a-standard-library-name-that-imports-by-a-string-is-a-trojan-horse.md), which left it open on purpose.

**Reason.** `typing.get_type_hints`, `typing.ForwardRef`, `inspect.signature(eval_str=True)`, `inspect.get_annotations(eval_str=True)` and `functools.singledispatch` evaluate a string annotation in the global names of its module. CPython 3.12 imports `app.lib` for `x: "__import__('app.lib')"`. The rule `forbidden_dependency` gave PASS with no gap. A site for each call of `typing.get_type_hints` was refused: 12 files of datamimic-ce call it.

**Decision.**
1. The survey parses each string in an annotation position (a parameter, a return, a variable) and the first argument of `ForwardRef` as an expression. Strings inside the annotation count too (`list["..."]`).
2. It reads the expression with the rules of the module. A hazard in it (a trojan horse name, a standard library importer of AD-1059, a re-exported name of AD-1094) is a `dynamic_import` site. The site stands at the string.
3. The text runs in the global names of its module. The walk of the text uses no proof, no inert read and no local name of the real tree. A range in the text is no range in the file.
4. A text that does not parse is no site: CPython raises a `SyntaxError` and imports nothing.
5. The strings of `Literal[...]` are values, not annotations. They are not read.

**Rejected.**
- A site for each call of `typing.get_type_hints`: it refuses ordinary code.
- A site for each string annotation that holds a call: `"Annotated[int, Field(gt=0)]"` is common and imports nothing.

**Limit.** A string annotation that holds a hazard and is never evaluated is a site (precision loss). A string that reaches `get_type_hints` through `__annotations__` or `setattr` is not an annotation position and is not read; the write rules of the survey apply to it. A type alias statement (`type X = "..."`) is lazy and is not read.

**Tests.** `tests/test_collector_false_pass_python_annotation.py` (CPython 3.12 imports `app.lib` in each plant; the verdict must be UNKNOWN or FAIL; each control stays PASS) and two unit tests in `hazards_importers_tests.rs`. The mutation that makes `parsed` return `None` fails 7 of 8 plants.
