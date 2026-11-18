# AD-935 A proven class literal is no import door

Status. Accepted. It amends [AD-894](ad-894-a-plain-statement-is-no-import-door-in-the-python-survey.md).

Issue #1847 reports a `dynamic_import` gap for `Plan.code`. The scan knows the class and its
literal value. Python does not run an import to read this value.

## Decision

Drop the gap at a plain `Plan.code` load only when the survey proves all of these facts:

- One direct `from` import binds the receiver. No other statement or parameter binds that name.
- The import names a class defined once in a scanned module, not a package re-export.
- The class has no decorator or custom base or metaclass. Its body binds `code` to a scalar
  literal and runs no other code.
- The scan finds no write that can replace the class, the import binding or the attribute.
  An attribute helper that can retrieve a writer also stops the proof.

The existing premise still applies: code outside the scan roots does not write bindings of
scanned modules or classes. The survey also retains the gap when it detects such a write.

The survey discharges all candidate loads together. If a source is unread or another import
door remains open, the scan cannot rule out an indirect write and retains the candidate gaps.

## Rejected

Do not treat every imported class as safe. The class can hold the `code` module, a descriptor,
or a value that a metaclass supplies. Code in another scanned file can replace the attribute.

Do not remove `code` from the door table. A read of the real module and calls such as
`code.interact()` keep their gaps. A package re-export needs a separate import identity proof.

## Tests

`native/python/src/survey/hazards_proved_tests.rs` checks direct loads, aliases, writes in another
module, missing definitions, descriptors, and custom bases and metaclasses.
`tests/test_cli_python_import_environment.py` checks the three lines from #1847 and runs Python
witnesses for writes and descriptor dispatch. The gate test closes the dependency decisions
with `complete_requires` so the open decisions do not mask the scan verdict.

Undo: remove the `only_class_data_reads` proof from the survey. The original walk still emits the gap.
