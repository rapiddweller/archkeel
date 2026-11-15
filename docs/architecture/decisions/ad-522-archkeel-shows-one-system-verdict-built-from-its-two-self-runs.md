# AD-522 ArchKeel shows one system verdict, built from its two self runs

**Status.** Proposed. Part of #880. It extends AD-478 (point 6) and AD-462.

**Decision.**
1. ArchKeel is one system: the Python shell and the Rust core. A single run is not possible: one
   scan has one profile, one namespace and one collector reply, and `scan.language` takes one value
   (AD-478 point 6). The mounts of a contract tree hold the same language. A mixed tree needs a
   profile, roots and a namespace for each mount and one collector reply for each, joined in the
   model. That is a core slice of its own, and a rule "the shell reaches the core only through the
   binary" needs a rule kind that can name a process start. Neither exists yet.
2. Until then the system is two runs and one join. The verdict of the system is the weakest verdict of
   its parts: FAIL before UNKNOWN before PASS. A part without a result counts as UNKNOWN, never as
   PASS. The counts are the sums of the parts. The join lives in `tools/report_product.py`
   (`weakest`, `worst`, `summed`, `system_line`), outside `src/archkeel`, so it is no decision logic
   of the shell and the shell contract does not read it. The frame of each part holds its decision.
3. `make self-validate` prints one line for the system and one line for each part
   (`tools/self_system.py`). The pinned result of each part stays the gate.
4. The gallery has one page of the system, `self/index.html`, and one shield endpoint,
   `self/badge.json`. The page has one verdict card, the two parts as cards that link to
   `self/core.html` and `self/shell.html`, and the exceptions of each part, bounded. The entry
   `index.html` keeps its URL and shows the same page. The old files and their paths stay.
5. The README shows the badge of the system and no fixed count: the count is in the generated file.

**Reason.** The owner reads the report of ArchKeel as one system. Two badges let a reader take the
PASS of the shell for the verdict of the product.

**Rejected.** A joint verdict in the core for a tree of two languages: no collector reply joins them
today. A badge that shows PASS for the shell alone.

**Limits.** The join checks no relation between the parts. The process start of the shell is stated
on the page, not verified.

**Tests.** `tests/test_report_product_page.py` (the weakest verdict, an undecided part is UNKNOWN,
the card of the system comes first), `tests/test_report_gallery.py` (`self/index.html`, `self/badge.json`),
`tests/test_readme_showcase.py` (one self badge, the order of the first screen, no fixed count).
