# AD-648 A file that no import can name is a script and has no layout

**Status.** Proposed. Part of #880. Census class K3. It amends AD-450 and AD-564 (`layout.rs`).

**Reason.** A Python file such as `demo-custom-components/script/converter.scr.py` is read as the
module `…demo-custom-components.script.converter.scr`. Its file is not the path of that name, so the
survey gave it the gap `module_outside_layout` (effect: its layout is unknown), which held the layout
and ownership rules that read the module. No import can reach such a file, so there is nothing to
prove about its place in a layout.

**Decision.**
1. A file is a **script** when a part of its dotted name is no identifier (`demo-custom-components`)
   or its stem holds a dot (`converter.scr.py`: `import pkg.converter.scr` looks for
   `pkg/converter/scr.py`). The interpreter confirms both (`tests/test_cli_python_scripts.py`).
2. A script gets no `module_outside_layout` gap. It stays in the survey: its source is read, its
   imports are edges of its file, and its module name is checked for ownership as before.
3. It is no import target: no statement can spell its name, and a loader call (`import_module`,
   `exec` of a path) is its own gap with the effect `every_module`.
4. An identifier-named module whose top package lies above its scan root keeps the gap.

**Why sound.** The gap said "the place in the layout is unknown". For a file that no import can name
the layout has no fact to be unknown: the file is reached only through a loader, and each loader
call already holds every module. The edges that the script writes are not dropped, so a forbidden
import in a script is still found.

**Not done.** The text does not count the scripts ("7 script files are not modules"): the reply has no
channel for a note that holds nothing. The gain on the CE project (3 rules in the census) is not
measured here.
