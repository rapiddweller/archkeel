# AD-34 A declared inside is recorded, so the report draws it without reading a second contract

Amended by [AD-110](ad-110-inside-rules-use-the-shared-evaluator.md): green requires
evaluated import-site evidence, not declarations. Missing contracts remain UNKNOWN.
[AD-111](ad-111-recursive-inside-contract-tree.md) removed the one-level limit;
explicit nested contracts are loaded, checked and drawn recursively.

The original observation recorded each inside sub-component with packages,
`requires` and `parent_id`, folding the inside-contract digest into the contract
digest. `ir` derived inner verdicts from records alone. The view opened sub-components,
then modules using `level()` ([AD-24a](ad-24a-a-module-opens-the-same-way-and-its-interface-is-what.md));
unassigned modules kept their own cards. `complete_requires` made absence forbidden
([AD-32](ad-32-a-component-names-what-it-requires-what-it-does-not-name-is.md)); undecided
pairs stayed observed ([AD-24b](ad-24b-observed-is-not-undecided.md)).

`check`'s 23 inner edges had all been gray despite three permitted crossing edges
at 21, 6 and 2 import sites. Reading contracts during rendering would violate the
single-observation boundary ([AD-10](ad-10-the-report-draws-component-flow-as-intent-against.md)).
Reusing `component_responsibility` would overlap parent and child ownership, making
`owner_of` return `None`. Defaulting to green would falsely permit a future reverse
edge. Verdicts therefore require evidence, never fallback conformance.

Original checks: three child cards; the three crossing edges green by declaration;
nine same-child edges observed; `archkeel.check` unowned; exactly six top-level
owners. At that stage only one inside level was recorded; deeper contracts were unused.
