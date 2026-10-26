# AD-270 Merge identical guard-path states

**Decision.** `_GuardPathWalker.block` drops repeated states after each statement. A state is
the condition value, the unknown reason and the path nodes. Two equal states walk the rest
of the block in the same way, so one copy is enough. No rule, grammar or record changes.

**Reason.** An `if` with an unrelated test gave two equal states, one for each branch. Each
later statement then ran once for each copy. Twelve such blocks gave 8,191 records for one
function (2^(k+1) - 1). The copies reached the report. The same violation appeared 2^k times
in `architecture.json`, so one function with eight blocks made a 31 MB report in 15 seconds,
and eleven blocks passed the 1 GiB collector response limit and ended the scan. The cause
sits in the walker, not in the rule, and a project pays only when its contract declares a
`forbidden_effect_under_condition` rule.

**Effect on existing reports.** Every distinct record stays. Copies of one violation
disappear. A baseline that stored such copies shows them as resolved debt. `--write-baseline`
rewrites it.

**Rejected.**
- A cap on the number of records: it hides real paths and gives a wrong result without
  a signal.
- A memo of `writes_name` and `reads_name` per statement: it makes each pass faster but
  keeps the exponential count.
- A change to the downstream consumers: they are correct, and they receive the copies.

**Check.**
- `tests/test_guard_path_states.py`: records grow by one for each added block, for six
  condition shapes; 18 blocks finish in under 2 seconds with one record for the guarded
  call; the distinct records of a mixed function are exactly the expected ones; a write to
  the condition and a receiver attribute guard keep their results; 40 random functions keep
  the same records for their calls when an unrelated block is added; a guarded rule over
  12 blocks gives exactly one violation.
- `tests/test_guard_path_classes.py` splits the input into equivalence classes and compares the
  walker with a copy of the walker before this change (no merging). The classes are 30 statement
  kinds for a parameter condition and 32 for a member condition: plain, call, guard test (plain,
  negated, with else, elif), unrelated test, compound or comparing read, call in the test, walrus
  and assignment writes, reflective writes, return and raise, loops, `try`, `with`, `match`,
  conditional expressions, nested functions and classes, empty branches. It checks every kind
  alone and nested in five contexts, every ordered pair in five contexts, every ordered triple of
  the ten state-changing kinds, and doubled pairs: 14,130 functions. In each, the distinct records are equal
  and the new list is an ordered subsequence of the old. A second table pins the expected value
  and reason of a call after each kind. Seven deliberate faults in the merge line (no merge,
  merge on value only, on value and reason, on reason and nodes, on value and nodes, keep the
  first state, keep the last state) each fail these tests.
- Before the change, the record count for k blocks was 2^(k+1) - 1 (k = 12: 8,191); after, k + 1.
- A comparison of the old and the new walker over 34,930 calls of `guarded_call_paths`
  (30,430 on `src/archkeel` and the standard library, 4,500 on random control flow) gave
  the same set of records every time, and the new records were an ordered subsequence of the old.
