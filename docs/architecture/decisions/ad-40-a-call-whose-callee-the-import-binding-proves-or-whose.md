# AD-40 A call whose callee the import binding proves, or whose receiver is already typed, types its result from a documented table

`resolve.call_result_type` types constructors listed in
`receiver_types._CONSTRUCTORS` through resolved import bindings, including
`hashlib.sha256`, `argparse.ArgumentParser`, Rich `Console`/`Table` and `Path`.
A local class merely named `Table` does not match. For an already typed receiver,
`_METHOD_RETURNS` supplies documented return types, such as `add_subparsers`,
`add_parser`, `relative_to` and `copy`.

Results feed [AD-37](ad-37-a-receiver-whose-type-is-statically-obvious-resolves-the.md)'s
local receiver map with origin `documented`, or type a direct receiver such as
`hashlib.sha256(payload).hexdigest()`. They are `partially_resolved`: import
bindings prove the callable, documentation states its unchecked return type.
`source.own_scope` visits statements in source order to type forward chains.

These result methods were major remaining self-call gaps. Bare annotation names
would confuse project classes with library classes; reading project return
annotations would introduce general expression type inference. Use the closed
library tables instead.

Limits: chains run forward within one function. Later receiver rebinding does not
retroactively invalidate an already typed result. Unlisted returns end chains;
only listed construction routes count, including `hashlib.new` with a name argument.

The analyzer version rises ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)).
Checks: constructor locals, direct call receivers, two-step argparse chains and
non-import callees in `tests/test_analyzer.py`. Self `report` moved from
421/4,071 unresolved calls (10.34%) to 381/4,101 (9.29%). Project subclasses,
`console or Console()` and scanner `for` targets remained outside the table.
