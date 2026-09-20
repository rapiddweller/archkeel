# AD-33 A component's inside is a level, not a list of pairs

[AD-31](ad-31-deciding-inside-a-component-is-optin-and-only-for-pairs.md) governed the inside by
demanding a decision for every observed module pair there, which is the enumerate-every-pair model
[AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md) abolished one level up. It is retired and `complete_inner_decisions` is removed rather than
deprecated, because it was drafted and released in no version: the tags stop at 0.3.0 and no
contract outside this repository can carry it. One thing survives it, and the log is the only place
that argument lives: the expected set is the pairs the analyzer observed, never the product of the
modules, since `analyzer` holds 21 modules whose product is 420 pairs against 46 observed ones.
`requires` inherits that principle. The inside is governed instead the way [AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md) already decided, by
its own scan scope and its own contract, with its own components, their own `requires`, and one
`public` both levels declare alike. That became affordable only with [AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md): a second level on
`check` drafts 12 sub-components, which is 132 ordered pairs under [AD-15](ad-15-onboarding-is-a-decision-interview-the-code-proposes-the.md) but 23 `requires` entries,
and on `ir` 13 sub-components, 156 pairs against 15 entries. An inside can outgrow the whole top
level, which holds 6 components and 8 edges, so leaving it ungoverned by default hides the larger
half of the system. The report therefore names a component holding more modules than the contract
has components, or more edges among those modules than it has component edges. Both quantities are
already in the observation, which is what makes the trigger legal: [AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md) binds the view to one
observation, and what a second level *would* draft is not derivable from it, because drafting needs
a second scan at a narrower scope. Which of the two quantities is chosen does not matter, because
on this repository they agree on every component: `analyzer` at 21 and 47, `check` at 13 and 23 and
`ir` at 15 and 22 stand against 6 and 8, while `cli` at 4 and 3, `render` at 5 and 3 and `host` at
2 and 0 stay below. The draft-based reading would have called `analyzer` small on the strength of
3 drafted sub-components, which measures how a package happens to be cut rather than what it holds.
Depth itself stays optional ([AD-20](ad-20-a-level-is-its-own-contract-never-a-nesting-inside-one.md)): the report states that an inside is large, and the architect
decides whether to open it, because naming a size is evidence while opening a level is intent.
Check: no schema or model carries `complete_inner_decisions`, and the report names `analyzer`,
`check` and `ir` as larger than the top level while staying silent about `cli`, `render` and `host`.

