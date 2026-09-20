# AD-34 A declared inside is recorded, so the report draws it without reading a second contract


The observation carries a declared inside as a record kind of its own: one record per sub-component
with its packages, its `requires` and the `parent_id` of the component holding it, and the inside
contract's digest folded into the contract digest, so an edit inside changes what `delta` compares.
`ir` derives every inner verdict from those records alone, and the flow view opens a component that
declares an inside into its sub-components first and into its modules one level deeper, in the shape
`level()` already returns ([AD-24a](ad-24a-a-module-opens-the-same-way-and-its-interface-is-what.md)). A module no sub-component owns keeps a card of its own. No inner
pair is ever `undecided`: under `complete_requires` absence forbids ([AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md)), so a crossing pair is
covered or violated, which leaves [AD-24b](ad-24b-observed-is-not-undecided.md) standing as written. Reason: `check` declares three
sub-components, yet all 23 of its inner edges were drawn grey although the inside contract decides
14 of them, `entry` → `foundation` at 21 import sites, `entry` → `policy` at 6 and `policy` →
`foundation` at 2. Three cheaper ways to colour them were rejected. Reading the inside contract
while rendering breaks [AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md) and makes the picture depend on a file that need not be present.
Reusing the kind `component_responsibility` makes `check` and `entry` both claim every module below
`archkeel.check`, so `owner_of` finds two owners, returns `None`, and the five callers of
`component_owners` degrade in silence. Letting the state fall through to `conforms` the way the top
level does, violation else undecided else conforms, would make green mean unopposed rather than
covered, so a `foundation` → `entry` edge added later would still draw green; the verdict is derived,
never defaulted. Limit: one level down is recorded, so an inside declared within an inside is not
drawn and the report says nothing about it; a third level needs a pass of its own, and until it
exists a deeper contract is silently unused rather than silently wrong. Check: opening `check`
shows three sub-components, its three crossing edges carry
21, 6 and 2 and are green because `requires` names them, the 9 edges inside one sub-component stay
observed, `archkeel.check` appears owned by none, and `component_owners` still returns exactly the
six top-level components.

