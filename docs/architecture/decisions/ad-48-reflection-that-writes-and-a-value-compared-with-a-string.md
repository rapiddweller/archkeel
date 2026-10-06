# AD-48 Reflection that writes, and a value compared with a string literal, are decided, not only reviewed

`forbidden_construct` adds `setattr`, `delattr`, `vars`, `dunder_dict` and
`string_literal_compare`. Calls match bare names or `builtins.<name>` as written;
`dunder_dict` covers reads, writes and deletes of `x.__dict__`.

`string_literal_compare` records three syntactic forms:

- `==` or `!=` with a string literal or a proven local bound once to one.
- `in` or `not in` with a non-empty tuple, list or set of those values on the right.
- `match` with a string literal value pattern at any case depth.

Record once per comparison node or whole `match`, with `form` identifying compare,
membership or match ([AD-29](ad-29-a-function-that-does-nothing-is-a-claim-not-a-stub.md)).
All expression positions count. Exclude only `if __name__ == "__main__":`, Python's
entry protocol. Whether a value needs `Enum`, `StrEnum` or `Literal` is an architect
decision scoped through `source` and `allowed_sources`.

Use `constructs`, not typing signals: otherwise additions would change typing
ratchets without a contract rule ([AD-8](ad-08-statement-constructs-are-class-a-rules.md)).
The self-contract adds the four reflection constructs to `CONSTRUCT-NO-DYNAMIC`;
the shop adds the string rule and five probes ([AD-11](ad-11-every-checkable-item-has-a-catalogued-demo.md)).
Analyzer version rises to 0.22.0 ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md));
contract 2.1.0 stays unchanged ([AD-27](ad-27-a-type-escape-hatch-is-decided-not-merely-observed.md)).

Issue #8 exposed missing reflection-write and string-vocabulary rules. Restricting
`string_dispatch` to branch positions would hide predicate comparisons and require
parent tracking, while false positives depend on values, not position. Measurements
found 151/181 self hits and 387/424 EE hits in branches; a 16-hit sample estimated
only about 44% real vocabularies, or 50% with branch filtering. PR 22 chose the syntax
name. Counting cases separately would overweight a ten-way vocabulary.

Limits: aliases, `object.__setattr__` and `operator.attrgetter` are unseen;
shadowed local names are reported. `getattr`/`hasattr` remain typing signals, so
reflection reads and writes affect different guardrails. String false positives
include foreign identifiers, trust-boundary parsing and already typed `Literal`
values. Empty-string comparisons count. Named sets, dict/frozenset membership,
literals on the left of `in`, `startswith` and dispatch dictionaries are unseen.
`x.__dict__.__dict__` records only the inner node to avoid identical-location ids.

Do not apply the string rule to self: 181 hits across 37/62 modules comprised
167 comparisons and 14 memberships, no matches. Leaders were `check/delta.py` 31,
`ir/codec.py` 19 and `render/summary.py` 17. JSON record/status values
([AD-2](ad-02-json-has-one-type.md)) and AST names dominate; exempting 171 non-CLI hits
would widen the contract without deciding useful policy.

Checks: analyzer probes cover reflection, all string forms, exclusions, unique ids
and scoped traceable violations. [AD-49](ad-49-an-allowance-may-name-its-module-exactly-so-a-package-root.md)
exact scopes and declaration exemptions carry all constructs. The contract corpus
accepts five kinds and rejects unreleased `string_dispatch`; the demo catalog runs
five probes. Self validation passed the widened reflection rule with zero hits.
