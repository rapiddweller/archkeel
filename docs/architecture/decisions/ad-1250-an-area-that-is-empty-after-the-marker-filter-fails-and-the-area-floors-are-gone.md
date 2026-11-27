# AD-1250 An area that is empty after the marker filter fails, and the area floors are gone

**Status.** Accepted. Owner decision of 2026-11-27 (drift gates audit, step A). Amends AD-674 and AD-736.

**Decision.**
1. `tests/area_floors.json`, the override `ARCHKEEL_FLOOR_PLUS`, the option `--tier` and the floor tests are deleted.
   A saved count of today's tests protects nothing: a test moved to another area or file made the number wrong,
   and nobody found a lost test with it (4 commits in November, all shard rebalances).
2. One check replaces them. `pytest_collection_finish` in `tests/conftest.py` fails a requested `--area` that
   holds no test after the marker filter (`-m`). It also fails when another requested area is not empty.
3. Unchanged: each test file belongs to one area (`tests/areas.py`), the CI matrix lists every area, and the
   aggregates fail closed.

**Protects -> still covered by.** An area that runs no test -> the new check. A test file with no area ->
`test_every_test_file_belongs_to_one_area_and_ci_runs_every_area`. A lost single test -> none (owner decision).

**Limit.** An area can lose most of its tests and still pass. Review of the diff and the test results shows
a lost test.

**Tests.** `tests/test_area_selection.py`, `tests/test_make_gate.py`.
