# AD-1055 A premised PASS reads "PASS under" its premises

**Status.** Accepted (owner decision, 2026-11-22). It changes the words of [AD-764](ad-764-a-pass-that-rests-on-a-premise-of-the-contract-reads-pass-assuming.md) and [AD-664](ad-664-a-contract-can-declare-the-reach-of-a-door-site.md).

**Reason.** "Assuming" reads as a guess of the tool. The premise is a claim of the contract. "Under N declared reaches" says what the PASS rests on.

**Decision.** The text, the page and the frame words read `PASS under <premises>`, for example `PASS under 3 declared reaches` and `PASS under 1 stated external user`. The summary reads `1 hold under 3 declared reaches`. The premise `standard_library_unchanged` reads `the premise that outside code leaves the standard library unchanged`. The frame keys (`assuming`, `assumed`, `premises`) do not change.

**Tests.** The Rust page tests and the text tests that assert the words.
