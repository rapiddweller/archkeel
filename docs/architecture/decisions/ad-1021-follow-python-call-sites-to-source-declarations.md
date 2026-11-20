# AD-1021 Follow Python call sites to source declarations

**Decision.** Explorer can link the spelling of a Python call to a candidate
declaration in the scanned source. Each link records the call site and declaration
separately. The inspector opens either location in the same snapshot. The map
groups candidates by direction separately from proven calls and imports.

Validation counts a public builtin method on an exact string or container
literal in the builtin bucket. A name, constructor call or formatted string
needs additional evidence about the receiver.

**Reason.** A developer can inspect where a name comes from even when runtime
rebinding prevents ArchKeel from proving which object receives the call.
Counting a matching name as a resolved call would also affect architectural
verdicts and checked stories.

**Limit.** A source candidate supplies neither a runtime target nor a checked
story hop. Two calls of the same name can have different bindings. The scanner
needs source evidence for both ends.

**Checks.** The collector exercises name binding and ambiguity. The Explorer
query test follows a grouped candidate to both files and verifies that the
same link cannot establish a story step.
