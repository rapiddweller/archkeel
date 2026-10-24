# AD-263 A cycle finding carries one concrete path

**Decision.**
- A `module_cycle` or `package_cycle` finding gets a `path`: the shortest closed walk through
  the cycle, as ordered steps `{source, target, location}`. `location` is the first import
  site that makes that edge (`file:line`), taken from the edge's import records.
- The path is computed once in `ir/findings.py`, from the SCC record and its internal edge
  records (`module_topology` / `package_topology`). So the terminal, the HTML and the JSON
  show the same path.
- The walk starts at the smallest member name and breaks ties by the smallest next name.
  The same observation always yields the same path.
- A package cycle's step shows the package edge and one module-level import site for it.
- A step records whether its import site is type-checking-only, so the reader can see
  which edge is cheapest to remove.
- The finding keeps its member list and size. A large SCC shows the shortest path and the
  count of edges not on it, never the whole edge list.
- Result schema: `findings[].path` is optional and additive. An older reader ignores it.

**Reason.** #678 (fastmcp: a 63-module, 10-package SCC). The report names the component set and
the first location, `src/fastmcp/__init__.py:5`, but not the edges that close the loop. The user
rebuilds the cycle by hand from a 5.8 MB artifact, or edits the contract instead of the code.
Every fact needed is in the observation already: the SCC record lists its internal edges, and each
edge lists its import records with evidence.

**Rejected.**
- Print every edge of the SCC: 243 edges is not an answer.
- Find all elementary cycles: exponential, and nobody reads them.
- Compute the path in the renderer: the terminal and JSON would drift from the page.
- Add a `cycle` command: the finding is where the user already looks.

**Limit.** One path is one way to break the cycle, not the only one. A call edge never appears:
cycles are built from import records only (`check/evaluation/topology.py`).

**Check.**
- A fixture with a 3-module cycle yields the path `a → b → c → a` with the three `file:line` sites.
- A two-package cycle shows the package edges with a module site each.
- The same input in two runs, and under reversed file order, yields an identical path.
- An SCC of 63 modules yields a path no longer than the SCC, plus a count of edges left out.
- A type-checking-only edge is marked.
- `findings[].path` validates against the result schema; a finding of another kind has none.
