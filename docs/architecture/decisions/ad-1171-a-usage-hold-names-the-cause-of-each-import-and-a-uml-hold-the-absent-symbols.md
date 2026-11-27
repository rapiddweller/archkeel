# AD-1171 A usage hold names the cause of each import and a UML hold the absent symbols

**Status.** Accepted. Part of #2089. Builds on [AD-1210](ad-1210-an-interface-hold-names-the-cause-of-each-held-import-and-pair.md), which states the cause of a withheld route on each import. No verdict, rule or gap changes: only the text of two reasons.

**Reason.** On a copy of EE (`560d5c7ef`), 1,128 `interface.usage_unknown` gaps said "import seen, no proven use", and the UML target said "absent symbol: the symbol inventory is not complete" for 55 assessments. Neither named the import, the module or the cause.

**Decision.**
1. **Usage hold.** An `import_seen` gap now reads: `Cause of each of N imports: <count> <class>, ...` and `First: <source module> imports <name>, <class> (<module or hop>)`. The class of an import is `call_form`, `unbound_type`, `other_symbol` (the route names another symbol), or the word of the `RouteWithheld` cause of AD-1210 (`escaped_*`, `outside_write`, `unread_all`, `uncertain_hop`, `ambiguous_reexport`, `type_checking_reexport`), or `not_stated`. `RouteWithheld::as_str` is the one source of the word.
2. **UML hold.** A symbol of the target that the inventory lacks is named in the reason of the row: up to five qualified names, then "and N more". Each name carries its module and the cause that an import states for that module (`escaped`, ...), or "no cause stated". The stable key of the reason does not change.
3. **Measured** on the EE copy (with the escape causes of #2117): of 1,128 holds, 1,006 have `escaped_name` as the first cause, 57 `escaped_value`, 53 `other_symbol`, 12 `outside_write`. Of 49 UML assessments, the first five absent symbols are named, each with its module, the cause and the place of the escaping use. On the CE copy all 525 holds are `outside_write`.

**Not done.** The cause names the use that hands a name on (`datamimic_ee.authoring <- datamimic_ee/interfaces/cli/authoring.py:145` for `build_authoring_reference`), but the collector still withholds the module. Narrowing that rule needs its own proof (#2106).

**Rejected.** A new field on the wire for the cause of each module: the import record already states it (AD-1210).

**Tests.** `tests/test_cli_python_usage_unknown_cause.py` (a plant for `escaped_value` and for `unread_all`, and a control with a proven use), `tests/test_cli_python_symbols.py` (the absent symbol is named). Mutations: a constant class word fails the two plants; a missing name list fails the symbol test.
