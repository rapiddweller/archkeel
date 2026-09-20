# AD-32 A component names what it requires; what it does not name is forbidden

[AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md) makes every
ordered component pair a decision, so n components cost n·(n-1) rules: Archkeel's six components
carry exactly 30 of them, 22 prohibitions and 8 permissions, for the 8 edges the analyzer actually
observes. The cost is not this level but the next one. A second level on `check` drafted 12
sub-components and asked for 132 decisions ([AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)), four times the whole top level, which is why a
component's inside has never been described by its own contract: the file split is not blocked by
the split, it is blocked by the pair model. A component therefore declares `requires`, the
components it may import, beside the `public` it already offers, and each entry carries the
architect's reason. A pair absent from that list is decided, not open, forbidden by the same closed
world `complete_assignment` uses for modules; so the two lists compose the way [AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md) already
requires, one naming what crosses outward and one what crosses in. The rule kind `complete_requires`
makes the list checkable the way `interface_boundary` makes `public` checkable: a cross-component
import no `requires` entry covers is a violation naming the importing module, and without the rule
nothing changes: the rule is the gate, so no repository inherits this work by upgrading ([AD-31](ad-31-deciding-inside-a-component-is-optin-and-only-for-pairs.md)).
Under the rule no pair is ever open, because absence decides; open means only that a component
named by the rule has no list at all. `init` writes neither the rule nor a list, because a list it
wrote would decide the pairs [AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md) reserves for the architect, so a freshly drafted contract is
unchanged. [AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md) ties two levels together partly by checking that nothing inside a component
imports what the level above forbids; under this decision that term is the complement of a
`requires` list rather than an enumeration of prohibitions, and [AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md) is to be built against that
reading. Archkeel's own 30 pair rules become 8 entries, one per
observed edge and no more, because its permissions and its observation already agree exactly.
Limit: `requires` speaks about components, so the 11 rules that narrow a pair below package level, a
forbidden target module or a `target_symbol` or `allowed_sources`, survive unchanged; and
`decided_by` moves from the edge to the rule, so the report counts one decision where it counted
eight. Contract `schema_version` stays 2.1.0, because `requires` is an optional property on a
component that forbids no existing one and a new rule kind makes no valid contract invalid, while
older Archkeel versions fail closed ([AD-8](ad-08-statement-constructs-are-class-a-rules.md)). Check: a shop probe whose `render` component imports
`model` without requiring it yields exactly one violation, the contract corpus pins both the rule
and a malformed `requires` entry, and `init` on a fresh repository drafts no `requires` list.
Archkeel's own contract adopted the rule in a step of its own: it now carries the 8 entries above,
one `complete_requires` rule and 25 rules in total, where the 30 pair rules used to be.

