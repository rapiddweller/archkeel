# AD-851 A module that only declares names cannot dispatch

**Status.** Accepted.

**Reason.** AD-806 can report a trait dispatch gap from a file that only imports names
and declares modules. Following an import from such a file proves reach, but it does
not supply a site that can run an impl.

**Decision.** A file with only inert imports and module declarations cannot run a
trait impl. Check inline modules in the same file. A declaration of a module in another
file has no body here. Keep the dispatch candidate when the file or its enclosing
declaration may be rewritten by an attribute. Other syntax can contain executable code
or a macro expansion, so it keeps the candidate.

**Rejected.** Count only explicit method calls. A value can run an impl when Rust drops
it or uses an operator, without a method call in the source.

**Tests.** A file that only re-exports a constructor passes the forbidden dispatch rule.
An inline re-export alone also passes. A drop in an inline module or in a macro expansion
gives FAIL or UNKNOWN.
