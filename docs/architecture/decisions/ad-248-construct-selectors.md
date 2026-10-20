# AD-248: Construct selectors stay nominal and closed

`forbidden_construct.selector` chooses one qualified receiver, member and access
or comparison role. Its literal is required for equality, membership, `match`,
`startswith` and `endswith`; constructor and type-probe roles select the nominal
type directly. The selector is a closed record, not a predicate language.

The Python observer records direct accesses through a uniquely annotated
receiver, positional `getattr` and `hasattr` literal names (including static
string aliases), direct local constructors and `isinstance`/`issubclass`
probes, equality in either direction, literal membership, `match` value
patterns, and selected string predicates. It keeps read, write, call, reflection
and comparison roles separate. Proven unrelated receivers are ignored. Dynamic
names, ambiguous receivers and missing selected subjects remain UNKNOWN; known
violations remain FAIL beside uncertainty.

The evaluation receipt carries the selector and complete selector-fact
inventory for the selected source modules; the saved report binds source,
contract and schema identities. The selector requires contract 3.11 and its
source facts require observation 2.6; older readers preserve prior formats and
reject selector vocabulary relabeled to an older version. Other language
profiles do not claim this Python evidence.

The observer does not infer arbitrary values, follow general control flow,
parse snippets, or infer runtime types from a variable name. Unannotated or
mutated receivers stay UNKNOWN. Tests cover both equality directions,
unrelated receiver controls, dynamic reflection, constructor and type probes,
and saved report decoding.

The native full collection uses SourceFacts protocol V5's lossless compact rows so
the complete selector evidence remains within the existing bounded collector output.
The V4 provider survey and all V1–V4 wire formats remain unchanged; V5 expands before
the existing strict facts validator runs.
