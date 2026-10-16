# Dart nominal control boundaries

The Dart Python implementation separates immutable syntax values from parsing.
`syntax.py` owns the existing DTOs and finite semantic categories; `parse.py`
retains compatible DTO reexports and owns Tree-sitter extraction. A private
parse-local node view decodes each raw node kind once, caches identity within
one tree, and continues traversing unknown grammar nodes.

`resolve.py` consumes nominal syntax categories and owns resolution outcomes
and its extra binding roles. Snapshot SDK state reuses the canonical
`ir.facts.RuntimeRequirementState`; it does not declare a second SDK vocabulary.
Names, paths, excerpts and externally meaningful diagnostic text remain data.
URI, root, YAML scalar and Dart string escape recognition remain real grammars.

The inner Dart contract publishes named APIs and authors nominal field and
resolver return intent independently of observation. Whole-module Python
implementation guards cover syntax, parser, resolver, snapshot and collection;
this does not claim Dart-project `forbidden_construct` capability.

Native tests mutate actual source against unchanged Target intent. SDK-free,
directive, resolver, false-positive, UML acceptance and Compass demo tests
remain the behavior oracle. No exception or increased debt allowance is added.

Builtin URI classification belongs to resolution. The existing ResolvedTarget
carries its binary builtin flag to collection, which does not inspect the URI
scheme a second time. Local/external package/alias resolution remains unchanged.

The collection builder owns its emitted class categories and decodes that field
before using a previously built fact to decide mixin eligibility. Constructor
resolution retains its nominal status separately from the outgoing JSON builder;
policy dispatch does not read its own serialized status back as a string.

The five guarded Python modules do not include the `entry.py` process bootstrap.
Its `__name__` sentinel belongs to the separate runtime/bootstrap scope. Names,
paths, record IDs and open common record payloads remain data; there is no new
Dart-project construct capability or widened proof of analysis coverage.

The node view contains only 54 lines and delegates existing Tree-sitter
operations. Its 108 node/field kinds and 32 formatting lexemes are consumed by
this parser; they do not copy the external grammar. Eight immutable DTOs move
to `syntax.py`, where ten semantic vocabularies have one owner. The private
cache is cleared in `finally`, including failed parses. Unknown node kinds
continue exposing their children and never become a known default.

Against the final shared-wire predecessor, product Python grows by 930 lines;
much of the diff replaces terse string comparisons with explicit owned types
and wraps the resulting longer expressions. The inner Target grows by 1,139
JSON lines to bind actual DTO owners, nominal fields and used APIs. It contains
no historical report snapshots or second enumeration of the parser grammar.

Verification after the final resolver/fact status-domain separation:

- [Hosted source and native checks](https://github.com/rapiddweller/archkeel/actions/runs/38949475367): 357 Dart tests, strict mypy across 133 source modules, Ruff, 11 hygiene checks, native source mutations and the ordinary amendment writer passed.
- The native run measured zero violations, 52 typing positions, 58 unknown positions and 871 unresolved calls. The actual shared-wire predecessor had 918 unresolved calls; the baseline tightens to 871, with no increased allowance or exception.
- All 111 complete Compass syntax projections match the original parser exactly. Five full-fixture parse batches measured a median 2.94 seconds originally and 4.80 seconds with nominal nodes. The additional 1.86 seconds is a real parse cost; this change makes no report-rendering performance claim.
- [Compass, Flutter and Chromium checks](https://github.com/rapiddweller/archkeel/actions/runs/38949500731): 24 passed, including complete project reports, navigation and mutations. The existing conservative analysis unknowns remain visible.

The normal amendment binds the actual final shared-wire predecessor
`1f9cd588c21d2e485e8d7cf75b4c7a7e41ba793d`, the root policy and the measured
baseline. Independent final Astra review is still required before merge.

The resolver outcome domain retains its original three meanings: resolved,
unknown and unresolved. The collector separately owns the three emitted fact
statuses: resolved, partially resolved and unresolved. Shared spellings refer
to the resolver enum definitions, and collector decisions retain the nominal
fact status rather than reading it back from JSON.

Independent review added a semantic comparison against the actual predecessor:
all 58 budget-relevant UNKNOWN positions, their per-rule counts and all 20
recorded reexport routes have no additions or removals. Location/evidence IDs
are intentionally excluded from this semantic comparison.

Keyword recognition intentionally fixes four original substring false positives:
`staticValue`, `finalize`, `constellation` and `translate` no longer mark ordinary
fields as static, final, const or late. Real keywords and required parameters
remain positive. A focused regression records both sides of this distinction.
The 111-project-file equivalence claim is specific to the Compass corpus.

A smaller decoder was also measured in [a separate hosted comparison](https://github.com/rapiddweller/archkeel/actions/runs/38949613298): deriving lookup dictionaries from the actual enum members preserved all 111 projections but changed the median only from 4.668 to 4.516 seconds (~3.2%). No additional global lookup tables were added for that small measured difference.
