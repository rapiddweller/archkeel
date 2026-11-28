# AD-1520 The frame names the absent symbols of a UML target hold

**Status.** Accepted. Builds on AD-1171 and AD-1210. Closes #2242.

**Decision.** The `explain.holds.rules[UML-TARGET-...]` entry of a UML target row that has
assessments that the core cannot decide has the kind `uml_assessments` (it was `other` with total 0).
`total` is the number of undecided assessments. `uml` holds:
- `kinds`: the kinds of undecided assessment;
- `absent`: each symbol of the target that the symbol inventory lacks, with `module` (the module that
  should hold it), `class` and `at` (the cause that an import states for that module, and its place);
- `classes`: the count of absent symbols for each class (`escaped_name`, `outside_write`, ...,
  `no_cause_stated` for a module with no stated cause, `no_module` for a symbol with no module in the scan).

The text of the reason keeps its first five symbols. `AbsentSymbol` is a plain value in the model.
No verdict changes.

**Reason.** The frame named no module or site for the rule on EE, so the cause could not be
checked. The text named the first five symbols; the JSON had no list.

**Limit.** The rule stays UNKNOWN until the module that withholds the symbol records is released
(AD-1220 names the use) or the symbol is declared.

**Tests.** `test_cli_python_symbols.py` checks the typed hold of an absent attribute.
`test_cli_report_explain.py` checks the kind of the UML row on a real project.
