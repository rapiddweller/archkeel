# AD-646 A Python range that reaches 3.11 is read as 3.11

**Status.** Proposed. Part of #880. Census class K14. It amends AD-636.

**Reason.** AD-636 selects the target from the lower bound of `requires-python`. A project with
`requires-python = ">=3.10"` (pydantic) then had its whole run refused, although the range holds
supported versions, and the user had to write `python = "3.11"` in `[scan]`.

**Decision.**
1. The target is the lower bound of the range, but when that bound is below 3.11 and the range still
   holds 3.11 (no upper bound, or an upper bound above 3.11), the target is 3.11, the lowest version
   of the range that the collector supports.
2. The description says so: `ArchKeel reads this project as Python 3.11 (from requires-python
   ">=3.10" in pyproject.toml; Python 3.10 is not supported, so the lowest supported version inside
   that range is used)`.
3. A range that ends at or below 3.11 (`>=3.9,<3.11`) selects no supported version and keeps the
   refusal that names `python = "3.13"`. A version written in `[scan]` is never changed.

**Why sound.** The scan reads the project as one interpreter. 3.11 is a version that the project
allows, so a verdict is a verdict for a real target; the text states which one. A project that needs
3.10 syntax or library tables still sees 3.11 tables, and the description tells the user so.
