# AD-652: A group says why it is a group, and a capped list names both numbers

Status: accepted (owner order, second UX test of 2026-11-16, #1349, #1352, #1354, #1351). Part of
#880. It amends AD-630.

1. A level of up to twelve boxes is drawn as it is (lead decision; AD-630 said six). A larger level
   is split into groups. A group says why it is one: its first line states that the level has N
   boxes, more than twelve, and whether it is grouped by a name prefix or by sorted ranges. A range
   group holds at most six boxes.
2. A list that the page cuts says so with both numbers, `The list shows 100 of 337 violated places`,
   with a link to the list. A count reads all places, never the cut list: the places beyond the cut
   are kept as data (`Places::hidden`) for the counts.
3. Target and Diff of a contract that declares no dependency show one line: `The contract
   declares no dependencies yet: N open dependency decisions.` The number comes from the gap that
   names the open decisions; the line has no number when there is no such gap.
4. A responsibility that `init` drafted (the word `TODO`) shows as `Responsibility not written yet.`
   in the box and its details. NEXT counts those components as a job.
5. NEXT names the one to three largest jobs, each with its count (violated places, components
   with no written responsibility, the causes of unknown rules or of gaps with no rule), and says
   how many more there are. A finding of a module that no component owns says to assign its package,
   a root package too.
6. A level without a layer order is laid out in rows that fill the view: a chain snakes from row
   to row, and its edges follow. The rows take the shape of the canvas (its width over its height,
   times 1.45, between 1.2 and 3) and the diagram is laid out again when the Explorer goes to the
   full window and back. 9 and 12 boxes open at 71% or more with readable titles. A level with a
   layer order keeps the layered layout. The bars at the bottom of the embedded Explorer stand
   outside the fitted area.
