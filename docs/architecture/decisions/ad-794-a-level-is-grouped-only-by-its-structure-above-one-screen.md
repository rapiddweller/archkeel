# AD-794 A level of the Explorer is grouped only by its structure, above one screen

**Status.** Accepted (lead review of the pydantic system report, 2026-11-17). Amends point 2 of AD-630. Part of #880, issues #1488 and #1603.

**Context.** AD-630 split a level with more than `READABLE` boxes (12 in the code, six in the text of AD-630) into groups: by a shared name prefix, else by ranges of the sorted names (`argument_markers to fields_set`). A range tells the reader nothing: the boxes in it share only their place in the alphabet. On the Rust part of pydantic the 16 components were drawn as three ranges. A component with many modules and no parts drew every module box (#1603), or, after #1643, ranges of sorted file names.

The view holds more than 12 boxes. A 1440 x 900 screen in full view holds 6 x 5 module boxes at the readable zoom of 85 percent (AD-620 floor, #1490): a box of 200 x 144 with the spacing of the layout takes 228 x 143 px of the canvas of 1380 x 782.

**Decision.**
1. One limit for every level: `ON_SCREEN = 30` boxes (`html_atlas_node.rs`). The payload states it as `module_box_limit`, and the Modules view reads it.
2. A level with more boxes is grouped by its structure only. The order is: the layers of a layer order (never split, AD-606), then the prefix that the names of the children share (`svc01_a`, `svc01_b`), as in AD-630. A child whose prefix no other child shares stays a box of the level. A group of one box tells the reader nothing.
3. A component with no parts and more than `ON_SCREEN` modules gets a directory box (`«package»`) for each directory of two or more of its modules. A directory with more than `ON_SCREEN` modules gets a box for each file prefix of two or more files (`lazy_*`). The first part of the file name at `_` is used first, then the next parts (`beta_agent_*`, `beta_session_*`). A prefix box that is still too large gets the boxes of the next part inside it. Many directory boxes of one component are grouped by their path prefix (`corpus/` → `corpus/openai`), as in point 2, and such a group is a directory box too.
4. Sorted names are never cut into ranges. A level that no structure splits is shown whole and the canvas scrolls (#1618). The structure that the code has is the honest picture. An arbitrary cut is not.
5. A directory box only places a module on the map. The module keeps its owner in the contract (`tree.owner`, the assignment of the payload). The fact sheet of a directory box says that the report made the box from the module paths and names the owner.

**Consequences.**
- pydantic, Rust part: 16 components on one level, no group. Self report: no range box. The level `survey/` of the Python collector shows 8 prefix boxes and 25 modules that share no prefix (33 boxes).
- A level can hold more than 30 boxes when its structure gives no finer split. Example: a generated folder of 158 files with distinct names (pydantic test corpus, `interactions/`). The page then scrolls. This is shown, not hidden.
- `GROUP:` boxes still say "Decided by architect" (#1644). The directory boxes do not.

**Rejected.** Ranges of sorted names (AD-630): they look like structure and are not. A larger limit only: 16 boxes then fit, but a level of 300 has the same problem. Grouping by size into balanced buckets: the same as ranges.

**Undo.** Set `ON_SCREEN` to 12 and restore the range branch of `group_names` and `RANGE` in `html_atlas_groups.rs` (git history of #1643 and before).

**Tests.** `html_groups_tests.rs`: no level of 12, 13, 80 or 226 components with a shared prefix holds more than `ON_SCREEN` boxes, and 40 names with no prefix stay one level with no range. `html_next_tests.rs`: 30 components are not grouped. 31 give three prefix groups and one box, and each group says why. `html_atlas_dirs.rs`: a large directory splits by file prefix, a prefix that every file shares splits at the next part, and files with no shared prefix stay one box. `tests/test_report_explorer_layout.py`: a Modules view of the self report over the limit shows only modules that share no prefix.
