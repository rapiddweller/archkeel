# AD-1173 A module that evaluates annotations holds each value it cannot name

**Status.** Accepted. Issue #2093. It extends [AD-1095](ad-1095-a-string-annotation-is-read-as-code.md) and [AD-1134](ad-1134-a-text-the-parser-cannot-read-and-a-run-time-annotation-are-sites.md).

**Reason.** The verification run of #2063 found forms that put a string into an annotation without a string literal in an annotation position. CPython 3.12 loaded `app.lib` through `typing.get_type_hints` in each case and the verdict was PASS: a write to `__annotations__` inside an expression, a name that gets its string from a tuple unpack, `:=`, `+=`, a `for`, a condition, `str()`, `.replace` or `.decode`, `ForwardRef(name)`, `TypedDict(..)`, `NamedTuple(..)`, `type("K", (), {"__annotations__": ..})`, an alias of `__annotations__`, `d["a"]` and `C.s` as annotation. A rule for each form leaves the next form open. This decision adds one class rule.

**Decision.** A module *evaluates annotations* when it names `get_type_hints`, `get_annotations`, `ForwardRef`, `_eval_type` or `evaluate_forward_ref`, or calls anything with `eval_str=`. In such a module each of these is a `dynamic_import` site:
1. Any reach of `__annotations__`, `__annotate__`, `__annotate_func__` or `__annotations_cache__` as a value (a read, a write, an alias, a call on it), and the string `"__annotations__"`.
2. A call of `TypedDict`, `NamedTuple` or `make_dataclass`, and `ForwardRef` with an argument that is no string literal.
3. A part of an annotation that is no type form: a call, a condition, a computed string, a lambda, a dict. The strings in `Literal[..]` and the metadata of `Annotated[..]` are no annotation and are not checked.
4. A name or attribute name in an annotation that the module binds to a value that may be a string. Bindings that taint: an assignment of anything but a string literal, a type factory call (`TypeVar`, `NewType`, ..) or a function; an unpack; `:=`; `+=`; a `for` or `with` target; a comprehension or `match` capture. `Alias = other` is as tainted as `other`.

A string literal that a name or attribute name holds is read as code (AD-1134), also through an attribute (`C.s`). The statement forms of AD-1134 stay a site in every module.

**Effect.** The class rule only adds sites. On the CE (`23bd48d9`) and EE (`560d5c7ef`) references the verdicts and the gap records are the same before and after (CE 176/99/1 and 1087 gaps, EE 256/223/0 and 1633 gaps).

**Limit.** A module that gets its annotations evaluated only by another module (a library) is not gated: the survey reads only the module itself. A parameter name used as an annotation, and a string that another module writes into this module, are not seen. A name that the module binds to a call result (not a type factory) is a site even when the call returns a type.

**Tests.** `tests/test_collector_false_pass_python_annotation_class.py` (24 plants, 5 controls; CPython 3.12 writes a counter line in each plant) and two unit tests in `hazards_importers_tests.rs`. The mutation that makes the class rule return no site fails 20 of the 24 plants. The other plants stay UNKNOWN through AD-1134.
