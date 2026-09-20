# AD-60 report --only, --rule and --component narrow what a rendered report shows, never what it judged

`report` gains three flags: `--only violations`, `--rule <id>` and `--component <label>`.
`--only violations` shows only the declared-rule violations table, hiding component flow,
component communication, review claims and size and coupling; `--rule` and `--component` each
narrow that table further, independently, and combine as an intersection. `--component` matches
a violation whose crossing touches it on either side, source or target: an import violation
crosses two components, and a filter narrowing to one area wants every violation touching it
either way, not only the ones it originates from. All three compose freely and read the same on
`--json`: a filtered `report` carries `report_filter` (the flags that produced it) and
`filtered_violations` (the records they select), both `null` on an unfiltered run, the same way
every other optional `RunResult` field reads `null` when it has nothing to carry.

`ir.baseline.select_violations(observation, report_filter)` is the one derivation: it builds on
`violation_rows` (AD-54), the same typed rows `violation_counts` (AD-51) already groups, so a
filter can never select a different set of violations than the ones a consumer's own
`violation_rows` call would call the same rule or component. `render_html` reads
`result.filtered_violations` for the violations table exactly the way it always read
`observation.records("violations")`, `report_summary` names the filter in the one sentence the
terminal panel and the HTML decision banner already share, and `codec.result_payload` serializes
`filtered_violations` with the same `_record_payload` every other record in `architecture.json`
already uses. One selection, three readers, never two derivations of what a filtered report
shows.

The filter never touches `architecture.json`: `canonical_report_bytes(model)` is built in
`run_report` before any filter argument is even read, so the canonical artifact a filtered run
writes is byte-identical to an unfiltered one's, and `declared_rules`, `violations_by_rule`,
`violations_by_component_pair`, the measured `violations` scalar and the exit code all keep
reading every violation, filtered or not (AD-51). A filtered result still announces itself
everywhere it is read: `report_filter` is present in `--json` exactly when a flag was given, the
HTML decision banner carries `data-report-filter="true"` and a `Filtered (...): N of TOTAL
violation(s) shown.` sentence, and the terminal prints the same sentence in its own panel - the
one place doing the announcing rather than three copies of the wording.

A `--rule` or `--component` naming nothing this observation declares is `filter_unknown`, a new
uncoded `DiagnosticKind`, exit 2: `select_violations` validates against
`ir.baseline.declared_rule_ids` and `declared_components`, the full contract domain (every rule a
`DECLARED_RULE` record names, every top-level `component_responsibility` label), not only the
ones a violation happens to cite today, so a valid rule or component with zero violations
correctly selects an empty, non-error result. An inside's rule keeps AD-36's
`<component>:<rule id>` prefix, since `_owned_rules` already renamed it before the observation
was built; `declared_rule_ids` needs no prefix logic of its own. `--component` only ever matches
a top-level label: `ViolationRow.source_component`/`target_component` always come from
`component_owners`, which reads only `component_responsibility`, never a sub-component's
`inside_component_responsibility` (AD-34), so naming a sub-component is correctly unknown rather
than silently matching nothing.

Reason: issue #7 - on a 452-module, 25,223-evidence-row codebase the report shows every
component, sub-component, module and function at once, with no way to see only what is red or
only one area. `--only violations` answers "hide passing and valid entries" and `--rule`/
`--component` answer "narrow to one area, one rule, one component" - the issue's own words -
directly from the one place a violation's rule ids and component pair are already derived.

Rejected: `--level`, the issue's fourth flag. AD-36 already prefixes an inside's rule id with
its component (`store:STORE-REQUIRES-COMPLETE`), so "level 1 only" is already `--rule` matching
no colon, or every `--rule store:*` id, without a second way to say the same thing (SPOT); a
`--component` facet already isolates one component's crossings. A deeper claim - "level 2 only",
one sub-component's own violations apart from its siblings - cannot be built at all without
changing what a violation *is*: `ViolationRow.source_component`/`target_component` are always the
top-level label (the paragraph above), so no data a `--level` flag could read distinguishes one
sub-component from another. Adding that would mean widening AD-54's typed row for a flag nothing
in this issue asked reliably for, the opposite of the minimum machinery this decision looks for.
Also rejected: filtering by rule *kind* (`forbidden_dependency`, `forbidden_construct`, ...)
instead of rule id - the issue asks for "one rule", and a kind is a many-rule facet nothing here
needs yet; a second, cross-cutting way to read a report's violations, duplicating
`select_violations` for `--json` alone - `render_html`, `report_summary` and
`codec.result_payload` all read the one selection instead.

Limit: `--component` only ever matches a top-level component (the paragraph above); a violation
crossing no component pair, such as a forbidden construct, an unassigned module or a component
cycle, matches no `--component` filter at all, the same limit `violation_counts`'s `by_component_pair`
already carries (AD-51). `--only violations` hides component flow, communication, claims and
structure entirely rather than filtering their own rows to the same rule or component: those
views are not built on `violation_rows`, and filtering them to agree would be a second
derivation this decision explicitly avoids; the `Complete ArchitectureIR inventory` section and
its link to the unfiltered `architecture.json` stay on every page, filtered or not, as the escape
hatch to what a filter hides. No demo catalog row exists for this feature (AD-11): AD-11 catalogs
rule ids and diagnostic codes a contract can produce, and a report filter is neither; its own
`filter_unknown` diagnostic kind is instead named by `fixtures/demo_catalog_validation.py`'s
`filter_unknown` row, evidenced by `tests/test_report_filter.py`, the way `missing_tool` and
`existing_files` already point at a dedicated test instead of a shop-sample overlay.

Check: `tests/test_report_filter.py`'s `test_rule_facet_narrows_filtered_violations_to_the_named_rule`,
`test_component_facet_matches_either_side_of_a_crossing`,
`test_rule_and_component_facets_combine_as_an_intersection`,
`test_only_violations_alone_selects_every_violation`,
`test_architecture_json_bytes_are_identical_with_and_without_a_filter`,
`test_a_valid_filter_never_changes_the_verdict_the_exit_code_or_the_full_counts`,
`test_unknown_rule_is_a_named_exit_2_diagnostic_not_a_silently_empty_report`,
`test_unknown_component_is_a_named_exit_2_diagnostic`,
`test_declared_rule_ids_and_components_are_the_full_contract_domain`,
`test_html_report_states_the_filter_that_produced_it`,
`test_only_violations_hides_every_other_section`,
`test_terminal_summary_announces_the_filter` and
`test_cli_report_json_output_is_filtered`, all against the `tour` demo variant (AD-11);
`archkeel validate --root . --json` on Archkeel's own contract, with `archkeel.ir.baseline`'s
`public` list carrying `select_violations` beside AD-54's three names.
