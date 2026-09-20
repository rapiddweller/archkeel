# AD-40 A call whose callee the import binding proves, or whose receiver is already typed, types its result from a documented table

`resolve.call_result_type` reads two shapes. A constructor
call, `hashlib.sha256()`, `argparse.ArgumentParser(...)`, `Console(...)`, `Table(...)` or
`Path(...)`, is typed when its callee resolves through the module's import bindings to a name
`receiver_types._CONSTRUCTORS` lists, so a local class that happens to be called `Table` never
matches. A method call on a receiver that is already typed, `parser.add_subparsers(...)`,
`commands.add_parser(...)`, `path.relative_to(...)` or `digest.copy()`, is typed when
`receiver_types._METHOD_RETURNS` names the documented return type of that method. Both feed the
same two places [AD-37](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md) reads: a local bound to such a call enters `_local_receiver_types` with the
origin `documented`, and a call written directly as the receiver of another call,
`hashlib.sha256(payload).hexdigest()`, is typed at the call site the way a string literal already
is. A `documented` receiver resolves `partially_resolved`, never `resolved`: the import binding
proves which callable is named, but what it returns is what the documentation says, which Python
checks no more than it checks an annotation, so [AD-37](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md)'s line between what the language proves and
what a document states stays where it is. To let a chain type in one pass, `source.own_scope` now
walks statements in source order, which the two callers it had before never depended on.
Reason: after [AD-37](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md), the largest remaining unresolved groups on Archkeel's own source were method
calls on exactly these results, `digest.update` on a hash object, `add_argument` on the parsers
`add_parser` returns, `print` and `add_column` on Rich's console and table, and `as_posix` on the
`Path` a `relative_to` call returns; none of them is a receiver a literal or an annotation names,
so [AD-37](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md) could not reach them, and every one of them is a stdlib or declared-dependency method
the source already fully states. Two cheaper ways were rejected. Adding annotation names such as
`Table` or `Console` to [AD-37](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md)'s annotation table was rejected because an annotation is matched by
its bare spelling, and a project's own `Table` class would resolve to Rich's methods; the
constructor path goes through the import binding instead, which names the module it came from.
Typing from a callee's return annotation in the analysed source itself was rejected because that
is expression-level type inference over project code, the general problem [AD-37](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md) kept out of scope;
this decision stays with a closed table of documented library types. Limit: a chain types only
forward through one function's own scope, so a receiver that is later rebound is not retroactively
voided for a local already typed from it; a method whose return type the table does not name ends
the chain; and only the listed constructors and returns are known, so `hashlib.new` with a name
argument is typed while a hash constructed by any other route is not. `ANALYZER_VERSION` rises,
because the same input now yields different call records ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)). Check: `tests/test_analyzer.py`
probes a constructor-bound local, a call written as the receiver, the two-step argparse chain, and
a callee that is not an import binding; `archkeel report` on Archkeel's own source falls from
421 unresolved calls of 4,071 (10.34%) to 381 of 4,101 (9.29%), and what remains is outside this
table by construction: `_Parser` in `cli` subclasses `ArgumentParser` in project code,
`terminal.print_result` binds its console with `console or Console()`, and `path` in the
scanners is a `for` target.

