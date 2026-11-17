# AD-710: The fact sheet of a layer or group aggregates its members, and findings read as words

Status: accepted (owner order, 2026-11-17, #1428). Part of #880.

1. A layer or a group of the Explorer has no contract text of its own. Its sheet says `This box
   groups N components of layer X (layer K of M)` (a group keeps the line that says why it is a
   group), then lists each member component with the first line of its own responsibility. The
   `Provides` list is the union of the public names of the members, and `Not responsible for` is the
   union of their boundaries. The core page writes these lines from the member rows; the page
   decides nothing.
2. A field with no content is not drawn: no `None`, no `Nothing stated`, no empty list under a
   heading. This holds for a component too: `Requires` shows only when the contract declares one.
3. A finding of a rule reads as words with the rule id small: `5 public names without a user
   (NATIVE-PUBLIC-HAS-A-USER)`, and the link goes to the first violation block of the rule on the
   page. Each rule row of the payload carries its words for one finding and for many
   (`plain_one`, `plain_many`); a kind without words is told by its contract word.
4. The sheet names its box: `Layer fact sheet`, `Group fact sheet` or `Component fact sheet`.
