# AD-1089 An `interface_boundary` hold names its imports

**Status.** Accepted. Part of #1963. It follows [AD-428](ad-428-the-interface-import-verdict-needs-a-known-binding-and-publication-proof.md) (publication proof).

**Reason.** An `interface_boundary` rule is UNKNOWN when an import has no proven binding or route. The row said only `interface_boundary: unread import binding`. It named no import. On EE 19 rules were UNKNOWN with this text, and a reader could not find the import that held the rule.

**Decision.**
1. `Reason::Interface` carries an `InterfaceHold`: the gap of the first undecided import, the count of undecided imports and the first five as `source -> target:name (form)`.
2. The text reads `interface_boundary: <form>: N imports (showing 5): a -> b:Name (<form>), ... and K more`. A hold with no import (the publication surface is not read) has the gap word only.
3. The stable key (AD-546) stays the gap word of the first undecided import. A baseline entry keeps matching, and a new import does not change the key.
4. The check collects all undecided imports. Before, it stopped at the first one. The verdict is the same: a hold stays UNKNOWN, and no rule moves to PASS.

**Rejected.**
- New fields in `explain.holds`. They change the frame schema and the shell for one text. The row text is enough to find the import.
- A line number for each import. The model import has no line. The module pair and the name find the import.

**Limit.** The list shows five imports. The count is exact.

**Tests.** `tests/test_native_interface_boundary.py::test_a_hold_names_the_import_and_its_form`, `native/model/src/causes_tests.rs`.
