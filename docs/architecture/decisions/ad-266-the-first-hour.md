# AD-266 The first hour: from no contract to a first overview

**Decision.**
- One written path for a person who has never used ArchKeel: `docs/getting-started.md`,
  linked first in the README's "Start here" and in `init --help`. Six steps: install; run
  `init`; read the overview; read the first verdict (a FAIL on a draft is the draft, not the code);
  choose between adopting the current state and writing the target; keep it green in CI.
- `init` ends with **Next steps** (three commands) and **First look**: facts, never advice and
  never a threshold. Lines: files parsed and the share of calls resolved; module cycles (how many,
  largest size); the most-imported module; the largest component; positions left UNKNOWN. A line
  says "none" when there is none. No line says "good" or "bad".
- `init --adopt` takes the current state into the contract. For every observed ordered
  component crossing it writes a `requires` entry with `decided_by: "agent"` and the rationale
  "Observed when the contract was drafted; not reviewed." It also records today's violations in
  `architecture-baseline.json`. The contract is then green today, and a new crossing or a new
  violation fails.
- Adopted entries stay visible as such: the guide (AD-265) and the report list them as
  "adopted, not reviewed", apart from entries a person chose. An architect confirms or removes
  them one by one; a confirmed entry changes its author and rationale.
- Plain `init` still writes no dependency rule. Existing imports remain evidence, not
  permission, unless someone runs `--adopt` and the file says so.
- `init` writes the guide (AD-265) as its last step.

**Reason.** A first-time user (and the people at the maintainers' companies) asked: what is
here, what is the goal, what works, what does not, and can I take the current state as the start?
Today `init` prints "Draft written", 132 open decisions and five heavy edges. The first `report`
says FAIL because of the unfinished draft, and nothing says so or what to do next. The pieces exist
(draft, baseline, report); the path between them is not written down.

**Rejected.**
- Adopting in plain `init`: it would hide a decision the README promises the architect makes.
- Words like "too big" or "healthy": they need a threshold ArchKeel cannot defend (AD-235).
- A `status` command: `init`, `report` and `guide` already hold the facts.

**Limit.** An adopted contract only stops new crossings. It does not say the current ones are
right; the "not reviewed" mark is the whole point.

**Check.**
- `init` on fastmcp prints Next steps and First look, with the 63-module cycle, the most-imported module and the largest component.
- A project with no cycles prints "module cycles: none".
- After `init --adopt`, `validate` exits 0; adding a new cross-component import makes it exit 1.
- The adopted entries read "not reviewed" in the guide and in the report; plain `init` has none.
- `init` without `--adopt` writes no `requires` entry.
- `archkeel guide` with no contract exits 2 and names `archkeel init`.
