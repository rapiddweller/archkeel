# AD-522 ArchKeel shows one system verdict, built from its parts (interim)

**Status.** Proposed, and an interim. Part of #880. It extends AD-478 (point 6) and AD-462. The
system contract (the core reads a system document, runs one scan for each part and gives one system
frame with its verdict by the one status rule of the core) replaces it. This record, `tools/self_system.py`,
the join in `tools/report_product.py` (`ORDER`, `weakest`, `system`) and the system part of
`tools/report_product_page.py` are deleted with the first slice of that contract.

**Decision.**
1. ArchKeel is one system. A single run is not possible: one scan has one profile, one namespace and
   one collector reply, and `scan.language` takes one value (AD-478 point 6). The mounts of a contract
   tree hold the same language. A mixed tree needs a profile, roots and a namespace for each mount
   and one collector reply for each, joined in the model. A rule "the shell reaches the core only
   through the binary" needs a rule kind that can name a process start. Neither exists yet.
2. The parts are in one checked-in document, `docs/architecture/architecture-system.json`, in the
   shape of the first slice of the system contract: a title and parts, each with an id, a title and
   the scan configuration it names. The language and the roots of a part come from its configuration,
   so no field that a contract reads names a language. The Makefile, `tools/self_system.py`, the
   gallery and the page take the title and the parts only from it (`tools/system_parts.py`).
3. The verdict of the system is the weakest verdict of its parts: FAIL before UNKNOWN before PASS.
   This ordering lives in one place, `tools/report_product.py`, outside `src/archkeel`, so the shell
   contract does not read it. The join does not trust the word of a result:
   - a part without a result, with a refusal, with no valid status or with another shape counts as
     UNKNOWN, never as PASS;
   - a status that its rule rows or its exit code contradict is the weaker of both;
   - parts from different commits, or run with different cores, are UNKNOWN with the cause
     "parts are from different commits" (or "different cores"); a FAIL stays a FAIL.
4. `make self-validate` prints one line for the system and one line for each part
   (`tools/self_system.py` runs `archkeel validate --config` for each part). The pinned result of
   each part stays the gate.
5. The gallery has one page of the system, `self/index.html`, and one shield endpoint,
   `self/badge.json`. The badge takes message and colour from the same join as the page, so a FAIL
   of one part is never hidden by a part without a result. The page says: interim; the verdict is
   joined outside the core; a system verdict covers the declared rules of each part; relations
   between the parts are stated, not verified. The entry `index.html` keeps its URL and shows the
   same page. The old files and their paths stay.
6. The README shows the badge of the system and no fixed count. Its language tiers are one block of
   `docs/known-limits.md`, and `tests/test_readme_showcase.py` keeps each copy in the README equal.

**Reason.** The owner reads the report of ArchKeel as one system. Two badges let a reader take the
PASS of the shell for the verdict of the product.

**Rejected.** A joint verdict in the core for a tree of two languages: no collector reply joins them
today. A badge that shows PASS for the shell alone. Trusting the status word of a result file.

**Limits.** The join checks no relation between the parts. The process start of the shell is stated
on the page, not verified. All parts lie in one checkout. The Python ordering is a second ordering of
the three words next to `run_status` of the core; it exists only until the system contract.

**Tests.** `tests/test_self_system.py` (pass and FAIL, UNKNOWN, a missing result, no JSON, `{}`, `[]`,
null and lowercase status, a refusal, a contradiction by rows or exit code, other commits or cores,
a third part), `tests/test_system_parts.py` (the document shape, no hard-wired part, a third part in
a copy of the document gives three cards and the weakest verdict), `tests/test_report_product_page.py`
(note and badge follow the verdict, the unit of each count), `tests/test_report_gallery.py`,
`tests/test_readme_showcase.py` (one self badge, the first screen, the language tiers).
