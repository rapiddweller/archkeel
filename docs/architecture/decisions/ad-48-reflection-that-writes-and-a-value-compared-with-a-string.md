# AD-48 Reflection that writes, and a value compared with a string literal, are decided, not only reviewed

`forbidden_construct` gains five constructs. `setattr`, `delattr` and `vars`
are calls matched as written, bare or as `builtins.<name>`; `dunder_dict` is any `x.__dict__`
read, write or delete. `string_literal_compare` is named for what it checks, syntactically, in
exactly three forms: a comparison where `==` or `!=` has a `str` literal, or a proven local name
bound once to one, on one side; an `in` or
`not in` test whose right operand is a non-empty tuple, list or set literal holding only `str`
literals or such names; and a `match` statement with a `str` literal value pattern at any depth of any case
(`case "a":`, `case "a" | "b":`, `case ["go", x]:`). It records once per comparison node,
however long its chain, and once per `match` statement, not per case, with `form` naming
`compare`, `membership` or `match`, the way `placeholder_body` records its spelling ([AD-29](ad-29-a-function-that-does-nothing-is-a-claim-not-a-stub.md)). It
records a comparison wherever it stands, in an `if` test, an assignment or a `return`, so the
name promises the syntax, not the intent: whether the compared value is a closed vocabulary an
`Enum`, `StrEnum` or `Literal` should declare is the architect's call, made with `source` and
`allowed_sources`, and precision comes from that scoping, not from the construct.
`if __name__ == "__main__":` is excluded: it is the interpreter's entry protocol, the only
spelling Python offers, and no enum can replace it, so counting it would turn every script into
an `allowed_sources` entry that decides nothing. All five are records in the `constructs`
section, collected by `constructs.py` under the owner scope that `allowed_sources` matches, and
`violations.py` maps them the way it maps `assert`. Archkeel's `CONSTRUCT-NO-DYNAMIC` now also
forbids `setattr`, `delattr`, `vars` and `dunder_dict`, with zero hits in its own source; the
shop sample gains `CONSTRUCT-NO-STRING-LITERAL-COMPARE` and one probe per new construct ([AD-11](ad-11-every-checkable-item-has-a-catalogued-demo.md)).
`ANALYZER_VERSION` rises to 0.22.0 ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)); the contract's `schema_version` stays 2.1.0 ([AD-27](ad-27-a-type-escape-hatch-is-decided-not-merely-observed.md)).
Reason: a "typed attributes only" rule could forbid the read side of reflection, `getattr` and
`hasattr`, but not the write side, and a closed vocabulary spelled as string literals could not
be forbidden in any scope (issue #8); `allowed_sources` already exempts the parsers and
user-string handlers that must compare strings. Rejected: routing `setattr`, `delattr` and
`vars` through the call-target table `getattr` uses, which makes them typing signals. Every
typing signal is a typing position and a `typing_signals` guardrail fingerprint, so any new
`setattr` in any checked candidate would fail `check` where no rule names it, a guardrail change
nobody decided; [AD-8](ad-08-statement-constructs-are-class-a-rules.md) kept `assert` and `broad_except` out of `typing_signals` for the same
reason, and `string_literal_compare` there would raise Archkeel's own 48 typing positions to 229.
Keeping the name issue #8 proposed, `string_dispatch`, and restricting it to comparisons that
choose a branch: the test of an `if`, `elif`, `while`, conditional expression or comprehension
`if`, directly or under `and`, `or` or `not`, plus `match` statements. Measured by position,
Archkeel's 181 hits hold 151 branch tests and `datamimic_ee`'s 424 hold 387, so the restriction
removes few records; weighting the per-position rates of a 16-hit sample (5 of 10 branch tests
and 1 of 6 other positions were a real closed vocabulary) moves the estimated share only from about
44% to about 50%, because the false positives lie in what is compared, not where.
It is also easy to step around: `return status == "ready"` in a predicate and
`is_ray = mode == "ray"` before `if is_ray:` would escape it while the same comparison in an `if`
would not, and branch position needs parent tracking the collector does not have. The architect
chose the name that states the syntax (review of pull request 22). One record per `case`,
because a ten-way `match` is one vocabulary and would otherwise weigh ten times a single `==`.
Excluding further idioms such as the empty string, because the definition stays syntactic and
scoping belongs to `allowed_sources`. Limit: matching is as written. `f = setattr; f(...)`,
`from builtins import setattr as s`, `object.__setattr__(...)` and `operator.attrgetter` are not
seen, and a module-local function named `setattr` or `vars` is reported, the alias and shadow
blind spots [AD-8](ad-08-statement-constructs-are-class-a-rules.md) names. `getattr` and `hasattr` stay typing signals, so the reflection family is
split across two sections: a new `getattr` moves the typing guardrail and a new `setattr` does
not. `string_literal_compare` cannot see what a type checker sees, so it reports three kinds of
false positive: foreign names, such as Python's own dunders and identifiers read from an AST
(`"__init__"`, `{"self", "cls"}`) or a driver string (`"mssql+pymssql"`); parsing at a trust
boundary, where JSON or user text is narrowed into a type (`value == "architect"` returning a
`Literal`); and a value already typed as a `Literal`, where strict mypy already rejects a typo as
a non-overlapping equality check. It also counts `name == ""`, and it does not see a named
constant set (`x in NAMES`), a dict-literal or `frozenset(...)` membership test, a literal on the
left of `in` (`"a" in text`), `str.startswith` or a dict used as a dispatch table.
`x.__dict__.__dict__` is one record, for the inner node, because both nodes start at one column
and would share one record id. Archkeel does not apply `string_literal_compare` to itself: its
source has 181 hits, 167 comparisons and 14 membership tests and no `match`, in 37 of its 62
modules, led by `check/delta.py` (31), `ir/codec.py` (19) and `render/summary.py` (17). They
compare record kinds and statuses read from JSON, which [AD-2](ad-02-json-has-one-type.md) keeps as `RawJson`, and Python names
read from the AST; the CLI's 10 are the only share an argument-parsing `allowed_sources` entry
would cover, and exempting the other 171 would widen the contract to pass rather than decide
anything. Check: `tests/test_analyzer.py::test_collect_constructs_detects_reflection_as_written`
and `::test_collect_constructs_detects_string_literal_compare_and_its_exclusions` (each positive
form, the main guard, the excluded forms, and unique record ids), and
`::test_class_a_rule_produces_one_traceable_violation` with a reflection rule and a
`string_literal_compare` rule whose `allowed_sources` exempts `sample.cli`;
`::test_exact_sources_scope_the_package_root_and_nothing_below_it` and
`::test_forbidden_construct_declaration_records_every_exemption` carry the new constructs through
[AD-49](ad-49-an-allowance-may-name-its-module-exactly-so-a-package-root.md)'s `exact_sources`, in the verdict and in the declaration record;
`tests/test_contract_model.py` accepts all five constructs in both the parser and the schema
through `tests/contracts/valid/forbidden-construct-scoped.json`, and rejects the unreleased name
`string_dispatch` in both through `tests/contracts/invalid/construct-renamed-string-dispatch.json`;
`tests/test_architecture_demo.py` runs the five new `class-a-construct-*` probes;
`archkeel validate --root . --json` passes with the widened `CONSTRUCT-NO-DYNAMIC`.
