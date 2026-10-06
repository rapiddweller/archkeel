# AD-49 An allowance may name its module exactly, so a package root is scoped on its own

`external_dependency_scope` and `forbidden_construct` add optional `exact_sources`.
`allowed_sources` retains prefix matching; exact entries compare equality.
External scope matches the importing module. Constructs match the owner module,
class or function body, excluding nested scopes. External rules require at least
one non-empty list. Old contracts keep their meaning.

Declaration records carry `allowed_sources` and non-empty `exact_sources`, exposing
all exemptions. Analyzer version rises to 0.21.0 for these records
([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).
The self-contract narrows `EXTERNAL-RICH-ARGPARSE-CLI`, `EXTERNAL-RICH-TERMINAL`,
`EXTERNAL-PACKAGING-RUNTIME` and `CONSTRUCT-NO-BROAD-EXCEPT` to their exact scopes.
`CONSTRUCT-NO-ANY` keeps codec and collector prefixes for nested annotation owners.

DATAMIMIC CE's root `dotenv` import and self `cli`'s `rich_argparse` had forced
prefix permissions across whole packages
([AD-28](ad-28-an-undeclared-external-dependency-is-a-hole-not-a-detail.md)). A separate
list avoids encoded string syntax and permits exact roots alongside allowed subtrees.
Changing prefix semantics would silently change old contracts. `allowed_modules`
would misname class/function scopes; inferring modules from longest owner prefixes
is ambiguous when functions and submodules share names.

Limits: `forbidden_dependency.allowed_sources` retains its existing exact meaning;
adding another exact field there would duplicate it. Rule-subject checks still use
`in_scope` per non-empty list, so an exact directory lacking `__init__.py` can appear
present through child modules.

Checks: analyzer exact-root and exemption-record tests; validation namespace checks;
valid/invalid corpus and round trips. Self validation passed four narrowed rules;
`rich_argparse` imported from `archkeel.cli.config` now yields `rule.violated`.
