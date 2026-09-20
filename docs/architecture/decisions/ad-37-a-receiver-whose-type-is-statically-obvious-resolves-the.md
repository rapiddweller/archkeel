# AD-37 A receiver whose type is statically obvious resolves the stdlib method it calls


`resolve_name` recognises three sources for a method call `recv.method(...)`: a str or f-string
literal written directly at the call site; a local name every one of whose bindings in the
function's own scope agrees on a list/dict/set/str literal or an unshadowed
`list()`/`dict()`/`set()` constructor call (an annotation of the same type is not a disagreement);
and a parameter or local whose only binding, if any, is an annotation naming `list`, `dict`, `set`,
`frozenset`, `tuple`, `str` or `pathlib.Path`/`Path`, generic subscript included. A second,
differently typed or non-literal binding of the same name — a plain rebinding, a `for`/`with`
target, a walrus or an unpacked assignment — voids the name for the whole function rather than
picking a winner, because which binding a call site actually sees is exactly the control-flow
question this cut does not attempt to answer. Each type carries a hand-written table of its
public methods, copied from the documentation rather than read with `dir()`, because `dir()`
answers for whichever interpreter happens to run the analyzer and [AD-7](ad-07-determinism-is-measured-not-assumed.md) requires the same source to
resolve the same way on every supported one. A literal proves its type outright, so it resolves; an
annotation is a declaration Python never checks at runtime, so it resolves only
`partially_resolved`, the same distinction `resolve_name` already draws between an indexed symbol
and a name that only matches one by tail. `_local_receiver_types` reads these bindings from the
function's own-scope walk that `bindings.py` already defines, moved to `source.own_scope` so both
read it instead of each re-deriving the same boundary: a nested function's own locals must never
leak into its enclosing scope's receiver map, and a second copy of that boundary is a second place
for it to drift. Reason: measured on Archkeel itself, 703 of 3,982 calls were unresolved (17.65%),
and classifying every one showed 621 of them (88%) were exactly this: `''.join`,
`diagnostics.append`, `items.extend`, `check.add_argument` and their like, stdlib container,
string, path and argparse methods on a receiver the source already states the type of.
`calls_unresolved` and `unresolved_ratio` are regression gates (`check/ratchets.py`), so this noise
moved the gate on every line the analyzer's own source added, never on a change to what it actually
calls. Three cheaper ways were rejected. Reading `dir(list)` at analyzer runtime answers correctly
today and wrongly on whatever Python version adds or removes a method next, which fails [AD-7](ad-07-determinism-is-measured-not-assumed.md)'s
determinism requirement outright. Inferring a receiver's type from every assignment along every
control-flow path is the general problem a static call graph cannot solve in Python at all; a
function that assigns `items` a list on one branch and something else on another stays out of
scope, because this cut answers only the receiver a single, unconditional literal or a declared
annotation already commits to. Resolving a call result's own type, as in `Repository(root).save(...)`
or `hashlib.sha256().digest()`, needs a second, expression-level type inference and stays unresolved
with its existing reason, so a method invoked on a call result is never conflated with one invoked
on a name whose binding this function can point to. Limit: a receiver two attributes deep
(`self.items.append`), a subscript receiver, and a name reassigned across branches to conflicting
types stay unresolved exactly as before; the table names only methods present on every supported
Python, so nothing version-specific is guessed into it. `ANALYZER_VERSION` rises, because the same
input now yields different call records ([AD-3](ad-03-the-analyzer-digest-decides-comparability-the-version-names.md)). Check: `tests/test_analyzer.py` probes each
resolution source once, a call-result receiver once, a method absent from the table once, and a
name rebound outside the table's proof — a plain reassignment, and a `for` target — twice;
`tools/classify_unresolved.py` re-run on Archkeel's own live source falls from 703 unresolved calls
of 3,982 (17.65%) to 421 of 4,051 (10.39%).

