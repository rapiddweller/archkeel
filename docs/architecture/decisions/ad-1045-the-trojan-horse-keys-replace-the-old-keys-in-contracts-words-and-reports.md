# AD-1045 The trojan horse keys replace the old keys in contracts, words and reports

**Status.** Accepted (owner decision, 2026-11-22). It renames the term of [AD-664](ad-664-a-contract-can-declare-the-reach-of-a-door-site.md). Old records stay as history.

**Words.** A trojan horse is a place that can load code the scan does not see; it is not a claim of malice.

**Reason.** The old word did not tell a reader that the site is a risk. A trojan horse says it.

**Decision.**
- Contract 3.20.0 names the key `declarations.trojan_horse_reach` and the form field `trojan_horse`. The field `name` and the field `count` stay as they are (AD-1043).
- The frame key is `trojan_horse_reach`. The code words are `trojan_horse_reach.unmatched`, `.ambiguous`, `.invalid`, `.inside` and `.declared`.
- The old key `door_reach` and the old field `door` stay valid as a deprecated alias in every contract version that had them (3.15.0 and up). The run gives the same verdicts as the new spelling and one note in the frame key `notes` (code `deprecated.trojan_horse_reach`). The note names the new keys.
- A contract that uses both keys `door_reach` and `trojan_horse_reach`, or both fields `door` and `trojan_horse` in one record, is a contract problem (exit 2). The new spelling reads in every contract version from 3.15.0 on, so that the canonical bytes of an old contract read again; `name` and `count` still need 3.20.0.
- A note is typed (`code`, `text`), never blocks, and changes no verdict. The text report prints one line `Note (<code>): <text>` for each note.
- A stored facts 11 file that spells the gap field `door` still reads (serde alias).

**Pins.** The pins of the self-check name modules. They are re-keyed: the set of gap records is the same, only the module names changed (`door` to `trojan_horse`). No pin is raised: 18393 gaps before and after.

**Tests.** `tests/test_cli_python_trojan_horse_alias.py`: an old contract (3.15.0, 3.19.0, 3.20.0) gives the same rows and the same exit code as the new spelling plus one note; both keys together are refused.
