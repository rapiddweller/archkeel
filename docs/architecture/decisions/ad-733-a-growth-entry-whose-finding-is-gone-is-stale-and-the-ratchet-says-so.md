# AD-733 A growth entry whose finding is gone is stale, and the ratchet says so

**Status.** Accepted. Part of #880, #1451 (S5). It amends AD-672. Owner approved the deletion of the stale entries on 2026-11-17. Visible change: check mode fails on a stale entry.

**Reason.** 22 of 23 entries of `native/expected-growth.json` and all 38 of the shell growth file named findings that the pin no longer holds (the `unused_public` rows were fixed in code). A stale entry is a standing licence: the same finding could return with no new reason. A missing base ref skipped the growth check without a word, and `native/suppressions.json` was not compared with main.

**Decision.**
1. An entry is live only while the pin holds its item (gap, violation, non-PASS rule status, UNKNOWN reason). `tools/native_expected.py` fails check mode on a stale entry. `--write` drops stale entries from the growth file.
2. The stale entries of both growth files are deleted (one entry stays: the UNKNOWN reason of `NATIVE-PUBLIC-HAS-A-USER`).
3. With `--base-ref` and no such ref the tool prints `ratchet: base <ref> unavailable, skipped`.
4. A suppression entry that `native/suppressions.json` adds against `origin/main` needs a `growth_reason` of at least 10 characters (`tests/test_born_small.py`).

**Rejected.** Keeping the entries as history (the decision log has the reasons); letting `--write` keep stale entries.

**Tests.** `tests/test_ratchet_stale.py`, `tests/test_born_small.py`.
