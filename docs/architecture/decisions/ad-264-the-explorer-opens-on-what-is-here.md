# AD-264 The Explorer opens on what is here

**Decision.**
- While nothing is selected, the Explorer's fact sheet shows an inventory instead of an empty
  prompt: the counts (components, modules, calls analyzed) and the components with the most
  modules, as a bar per component, largest first.
- It shows the 8 largest. A filter box narrows the list, and "Show all N components" opens
  it as a scrollable list. The list is never drawn in full by default, so a project with
  hundreds of components costs the same as one with twelve.
- A name in the inventory selects that component in the diagram, the same way a click on
  its node does. Selecting anything replaces the inventory with the fact sheet, as today.
- The inventory is drawn from the scene data the Explorer already holds. No new field enters
  the report payload.
- The verdict line says what the agent decided when it decided everything: "Draft contract:
  all N decisions are by the agent, awaiting the architect." Otherwise it keeps
  "Agent decisions a/b".
- The page order of AD-258 does not change: verdict, ranked findings, then the Explorer.
- The Explorer's top edge is pinned by a browser test: at 1440×900 it starts at or above
  y = 520, so no later block can push it down unnoticed.

**Reason.** #687. A newcomer runs `init` and `report` and gets FAIL with 18 findings, but
nothing says what the project consists of. The answer is in the diagram, in small print on
each node. The fact sheet beside it is empty on first load, at no cost in height, and an
extra block above the Explorer would move it from y = 477 to about y = 547 (on a 1280×720
screen it already starts at y = 587). Three layouts were drawn and compared with the
maintainer; this one was chosen.

**Rejected.**
- A strip above the findings: 70 px more height, and it reorders AD-258.
- Two columns: the Explorer becomes 400 px narrower, and the layout needs its own small-screen mode.
- An `overview` command: a new surface, while the report already holds the data.

**Limit.** The inventory is drawn by the Explorer script. Without JavaScript the Structure
overview table below the diagram remains the way to see the same numbers. Grouping 100+
components into areas is not part of this decision.

**Check.**
- With nothing selected, the fact sheet lists the 8 largest components with module counts.
- A project with 142 components renders the same 8 rows, a filter, and "Show all 142".
- Typing in the filter narrows the rows; selecting a name selects that node.
- Selecting a node replaces the inventory; clearing the selection brings it back.
- At 1440×900 the Explorer starts at y = 520 or higher (smaller y), on a fixture with 5 listed findings.
- The verdict line shows the draft wording only when every decision is the agent's.
- `make browser-runtime-check` passes with the regenerated runtime files.
