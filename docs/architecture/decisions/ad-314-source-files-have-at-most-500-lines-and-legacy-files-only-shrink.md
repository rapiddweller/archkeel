# AD-314 Source files have at most 500 lines and legacy files only shrink

Each tracked Python file under `src/` has at most 500 physical lines, counted as
`len(text.splitlines())`. The rule also covers each Rust file under `native/` and `crates/`, so it
is ready when the first native collector arrives. This amends [AD-4](ad-04-module-length-alone-does-not-justify-a-split.md).
AD-4 stays true: length alone does not justify a split. A file over 500 lines is a signal that
the file can mix responsibilities. A split must follow a responsibility seam, never a line count.

At the time of this decision, 57 of 172 files in `src/archkeel` are over the limit.
`tests/file_size_baseline.json` lists each one with its line count. The list is a ratchet:

1. A file over 500 lines must be in the list with its current count.
2. A listed file must keep its count. It must not grow. When it shrinks, its count must be lowered to the new size.
3. A listed file at or under 500 lines must be removed from the list.
4. A listed file that no longer exists must be removed from the list.
5. A new file over 500 lines fails.

Rules 2, 3 and 4 force the list to shrink and lock in each gain. A raised count is not a fix. Replaced code is deleted,
not split. New and replaced code must meet the limit at once.

**Why.** Large files hide mixed responsibilities and make review slow. Without a ratchet, a rule
that 57 files already break would fail at once, or nobody would enforce it.

**Place of the list.** The list lives in `tests/`, next to `tests/boundary_alias_legacy.json`. A
JSON file there needs no new inventory entry or workflow change. The test that reads it is in
`tests/test_repository_hygiene.py`, which is already in the `pr-test` list.

**Rejected.**
- A new rule kind in the product contract. No user needs it now (YAGNI). The rule can move
  there later without a change to its meaning.
- A limit for each function. AD-6 already lists long functions with a reason.
- No ratchet. A limit that fails 57 files on day one cannot merge.

**Limit.** The rule counts physical lines, with comments and blank lines. It does not cover
tests, `tools/`, or generated assets. A later decision can add them.

**Checks.** `tests/test_repository_hygiene.py` has three tests. One test checks the five rules on
temporary files. One checks which paths the rule covers. One checks the real repository against
the list and tells the reader how to fix each failure.
