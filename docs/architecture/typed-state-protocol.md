# Typed state protocol

State facts own five small control vocabularies: binding, referent mutability, object
mutability, property assignment and access. The Python collector constructs those enums
directly. Evaluation consumes nominal state events and enum values.

The state codec owns its private event tag, converts it once using its enum constructor,
and parses field controls into the domain enums. There is no parser exception to the
string-control rule. The old tuple-of-strings choice loop is removed. JSON field names
remain the wire schema; names, paths, annotations and evidence IDs remain data. NUL
validation is an explicit text grammar check and preserves its previous accepted inputs.

The encoder emits the original string values through enum values. JSON fields, event
order, null property assignments and malformed path rejection are unchanged.

The own contract protects both state_facts and state_codec with string_literal_compare.
Independently authored Target entities fix the five public field annotations; native
source mutation tests prove that widening them to str fails without editing the Target.
Native parser controls cover equality, membership, match and Final string aliases.
This is the state slice of #542; unrelated contract/graph/collector protocol vocabularies
remain separate migration work.
