# AD-630: The Explorer shows at most six boxes of a level, and each count names its list

Status: accepted (owner order, UX test of 2026-11-16, #1322, #1325). Part of #880.

1. Every diagram of the Explorer opens fitted to the view: nothing is clipped. The floor of 60% of
   AD-620 is gone: it cut a wide diagram at the edge of the window.
2. A level never holds more than six boxes (`READABLE`): in a chain of six boxes the whole level fits
   the width of the report column at a size that the titles can be read at. A scope with more
   children is split into groups, which are boxes of the tree: the children share a package
   prefix (`svc01_a`, `svc01_b`), else sorted ranges named by their first and last leaf. A group of
   groups is split again, with balanced sizes, so no range holds a single box. A violated place or a
   gap inside a group shows on the group. The boxes of a layer order are never split: the order is
   the picture that the contract draws. The first view of a run of 226 components shows two
   groups; the user opens a group to see its children.
3. The page states what each number counts, from the rows of its list: the card names `Rules PASS`,
   `Rules FAIL`, `Rules UNKNOWN` and, when the run has a gap that no rule owns, `Gaps with no
   rule`. The causes line states the number of causes, of unknown rules and of gaps with no rule that
   the Unknown section lists. The architecture line counts components without the boxes of
   layers, groups and parts.
4. A finding of a module that no component owns says what to do: assign the package of the module to
   a component, a root package too.
5. The details of a box say `Nothing stated in the contract` for a field that the contract leaves
   out, and `None` for a field that it states empty. No decision number stands in a text of the page.
