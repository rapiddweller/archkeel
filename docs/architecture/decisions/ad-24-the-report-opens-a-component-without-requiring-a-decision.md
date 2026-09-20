# AD-24 The report opens a component without requiring a decision

The flow view may open a
component and show its modules and the imports between them, derived from the same observation and
from no contract field. Where the component declares no inside, nothing there is decided, so those
edges are drawn as observed, never as conforming; a declared inside is recorded in that same
observation and decides the pairs that cross its sub-components ([AD-34](ad-34-a-declared-inside-is-recorded-so-the-report-draws-it.md)). Reason: the data is already measured and never shown: 142 module edges, 74 of
them inside a single component, with full module names. Looking inside costs nothing, while deciding
inside is [AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md) and costs a contract of its own. Limit: a further step into a module can only use
`symbols` and `calls`, and about one call in five stays unresolved, so such a view would show
structure without proving relations. Check: the opened view renders from `architecture.json` alone.

