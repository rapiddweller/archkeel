# AD-737: Python construct support is one map with downgrade and meet

Status: accepted (lead plan #1451, Wave 1 S2, 2026-11-17). Part of #880. Structural: no reply
byte changes.

1. Problem. The Python survey kept the support of five written constructs (`broad_except`,
   `dunder_dict`, `vars`, `string_literal_compare`, `getattr`) as five parallel `*_complete`
   booleans in four structs (the walk, the findings of one module, the findings of the run, the
   survey). They were folded with `&=` and mapped to `supported` or `partial` in the reply, and
   `any_annotation` and `dynamic_import` were fixed words in a separate list. A new construct had to
   add a field in each struct and a line in each fold. One missed fold is a construct that stays
   `supported` while a form hides it, and a `forbidden_construct` rule then passes on an absence
   that is not proven (`native/model/src/construct_match.rs`: only `Supported` or `Decided` lets an
   absence pass). That is a false PASS.
2. Rule. `survey/support.rs` holds one `Support` map keyed by `Construct` (each construct of the
   reply, in reply order). `Support::start()` states `any_annotation` and `dynamic_import` partial
   and each other construct supported. A form that can hide a site calls `downgrade(construct)`.
   The support of the run is the `meet` of the support of each module: each construct takes the
   worse of the two (`Partial` wins). The reply lists `Support::reply()`. The validation table names
   the constructs by `Construct::word`, so each construct word is written once.
3. The forms that downgrade a construct do not change: a non-broad or unproven except type for
   `broad_except`; any call for `dunder_dict`; a bare `vars` name or a call that is not the visible
   builtin for `vars`; a comparison, a `match`, a call or a `startswith`/`endswith`/`__eq__`/
   `__ne__`/`__contains__` attribute for `string_literal_compare`; a bare `getattr` name or a call
   that is not the visible builtin for `getattr`.
4. Proof of no change: the reply of the main collector and of this one, for the request of the
   shell self-check and of each Python fixture (E-runtime, F-architecture, H-uml,
   K-python-realworld, M-review-workflow, python-newer-syntax-demo, python-stdlib-demo), is
   identical after decompression except `code_digest`.

Proof: [support_tests.rs](../../../native/python/src/survey/support_tests.rs) (downgrade and meet
for each construct; a fixture per construct that the survey cannot see completely gives
`partial`, also beside a clean module); the rule stays UNKNOWN for each such form in
[test_cli_python_profile_limits.py](../../../tests/test_cli_python_profile_limits.py).
