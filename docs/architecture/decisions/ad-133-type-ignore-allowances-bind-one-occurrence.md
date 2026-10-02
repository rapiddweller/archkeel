# AD-133: Type-ignore allowances bind one occurrence

## Decision

`forbidden_construct.allowed_type_ignores` grants one exact suppression:

```json
{"qualified_name": "probe.operations.execute_sql_script", "line": 4,
 "statement": "client.execute_sql_script(query)", "tag": "[attr-defined]"}
```

All four fields must match. The statement uses `ast.unparse`; the tag is the
trimmed comment suffix after `type: ignore`. A standalone comment has no
allowable statement. Unknown fields and duplicate entries are rejected.

## Why and limits

A faithful native SQL invocation needs one explicit suppression (#228).
Module or function exemptions also permit unrelated constructs. Keep those
legacy selectors compatible; this allowance applies only to `type_ignore`.
An absent allowance preserves existing contract amendment digests.
An identical second suppression, cast, Any or reflection remains forbidden.

Line binding deliberately fails closed after a source shift. Review and update
the contract when that happens; a new or changed permission widens under
`--against`. No wildcards or separate approval mechanism.

## Evidence

The matched `type_ignore_allowance` fact cites its signal, source excerpt, rule
and existing decision provenance in JSON and HTML. `tests/test_exact_type_ignore.py`
checks neighbors, mismatches, nested/multiline owners, schema rejection,
round-trip encoding and real Git CLI widening/report runs. Demo rows
`class-a-type-ignore-exact` and `class-a-type-ignore-neighbors` show both outcomes.
