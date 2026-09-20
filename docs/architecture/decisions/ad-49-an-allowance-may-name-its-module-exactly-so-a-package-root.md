# AD-49 An allowance may name its module exactly, so a package root is scoped on its own


`external_dependency_scope` and `forbidden_construct` gain an optional `exact_sources` list
beside `allowed_sources`: an `allowed_sources` entry still allows its name and everything below
it, an `exact_sources` entry only the name itself, compared by equality where the prefix form
calls `in_scope`. For `external_dependency_scope` the name is the importing module; for
`forbidden_construct` it is the owner scope a construct is written in, a module, class or
function, so an exact entry exempts that scope's own body and not the scopes nested in it. An
`external_dependency_scope` rule needs one of the two lists non-empty, so `allowed_sources` is no
longer required on its own. A contract that never writes `exact_sources` parses, validates and
evaluates as before. The declaration record of both rule kinds carries `allowed_sources` and,
when it is non-empty, `exact_sources`, so the report shows every exemption a rule grants;
`forbidden_construct` recorded neither before, although both are evaluated. `ANALYZER_VERSION`
rises to 0.21.0 ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)): a contract may now yield records no earlier analyzer could, and every
`forbidden_construct` declaration gains `allowed_sources`. Archkeel's own contract narrows four
allowances to the exact form:
`EXTERNAL-RICH-ARGPARSE-CLI` (`archkeel.cli`, a package root with `config`, `skill` and
`__main__` below it), `EXTERNAL-RICH-TERMINAL` (`archkeel.render.terminal`),
`EXTERNAL-PACKAGING-RUNTIME` (`archkeel.analyzer.runtime`) and `CONSTRUCT-NO-BROAD-EXCEPT`
(`archkeel.cli.main`, whose one broad handler sits in `main`'s own body). `CONSTRUCT-NO-ANY`
keeps both prefixes: its `Any` owners are function scopes below `archkeel.ir.codec`, such as
`archkeel.ir.codec._raw_object:value`, and `archkeel.analyzer.embedded` is a package. Reason: a
package root is a prefix of every module in its package, so allowing a dependency the root
imports allowed it everywhere below; datamimic CE's `datamimic_ce/__init__.py` imports `dotenv`,
and `complete_external_scope` ([AD-28](ad-28-an-undeclared-external-dependency-is-a-hole-not-a-detail.md)) then forced exactly that over-broad entry. Archkeel had
the same gap: `archkeel.cli` allowed `rich_argparse` in `archkeel.cli.config` and
`archkeel.cli.skill`, though only `archkeel/cli/__init__.py` imports it. Rejected: an entry
syntax such as `"datamimic_ce:module"` inside `allowed_sources`, because every reader of the
list, both evaluations, `rule_scopes`, the namespace check in `validate`, the declaration record
and the schema, would have to parse one encoding out of a string, and `:` already separates a
module from a name in `public` entries and an owner from its parameter in typing-signal
records. Naming the list `allowed_modules`, as the issue proposed, because a `forbidden_construct`
owner is often a function, not a module, and one name should read the same in both rules. A
per-rule `exact: true` flag, because one rule could then not allow a root exactly and a subtree
by prefix, and two rules for one dependency each report the imports the other allows. Changing
what `allowed_sources` means, because every existing contract would change meaning without a
diagnostic. Matching a construct by the module its owner is written in, found as the owner's
longest scanned-module prefix, because that attribution is ambiguous where a function and a
submodule share a name, and a function's scope as a prefix already names it. An
`exact_sources` on `forbidden_dependency`, whose `allowed_sources` already match exactly, since
two fields would then hold one meaning. Keeping `ANALYZER_VERSION` at 0.20.0 because a contract
without `exact_sources` would have yielded unchanged records, because the version names what the
analyzer can record, not only what older contracts produce. Limit: `forbidden_dependency.allowed_sources` stays
exact under its old name, so the same word means exact there and prefix in the other two kinds;
and the rule-without-subjects check reads each non-empty list of an `external_dependency_scope`
as its own side with `in_scope`, so an exact entry naming a directory without an `__init__.py`
but with scanned modules below it counts as present. Check:
`tests/test_analyzer.py::test_exact_sources_scope_the_package_root_and_nothing_below_it`,
`tests/test_analyzer.py::test_forbidden_construct_declaration_records_every_exemption`,
`tests/test_validation.py::test_exact_source_outside_namespace_is_a_diagnostic`,
`tests/contracts/valid/exact-sources.json` and
`tests/contracts/invalid/external-scope-without-exact-sources.json` in
`tests/test_contract_model.py`'s corpus and round-trip tests, and
`archkeel validate --root . --json` passing on the four narrowed rules; importing
`rich_argparse` from `archkeel.cli.config` is now a `rule.violated` finding.

