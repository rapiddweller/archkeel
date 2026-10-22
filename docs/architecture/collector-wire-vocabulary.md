# Typed collector wire boundaries

Source facts own Language, RuntimeRequirementState, member inventory vocabulary and input roles. Runtime and Core ports explicitly reexport the same Language class. Protocol owns supported collector envelope versions, and resolver variants keep fixed Literal[Language.MEMBER] discriminators.

Codecs convert closed wire tags to private enums, then construct existing nominal ImportTarget and TypeShape variants. Runtime requirement states use one shared validator. Observation decoding consumes the profile's typed optional-section and unmeasured-scalar capabilities. Profile identity never selects coverage behavior.

JSON and TOML field labels remain declarative schema data validated by the existing exact-structure boundary. Module names, paths, source text and open profile-owned Record.kind values remain data. Path parser tokens, version gates, wire discriminators and columnar string sentinels are closed control vocabulary.

The existing v1/v2/v3 collector encodings, strict version rejection, old observation encodings and source dirty unknown spelling remain stable. Native tests observe actual codec source, reject equality, membership, match and Final-string controls, and weaken the real protocol-version annotation against unchanged authored Target intent.

V4 adds source-bound Python provider inputs and an explicit import-survey phase.
The survey preserves file coverage and parse gaps but cannot satisfy a full Python
observation. Native composition always follows it with full collection under one
shared deadline; custom collector wiring keeps its existing behavior. See the
[native evidence scope](target/design.md#native-evidence-extension) for proof limits.
Provider kind `declaration` links a lexical declaration to its captured provider
path, digest and evidence span. It does not assert registry contents, import
execution, runtime kind, callable signature or value shape.

The V4 `providers` survey discovers only requested source alias routes inside the
bounded collector. The parent re-reads their exact resolution inputs before full
collection; ordinary `imports` surveys and legacy protocols retain their scope.
Provider `alias` carries its publishing import, target and supporting evidence.
Missing or cyclic targets remain UNKNOWN. Provider facts never enlarge governed
files, imports or coverage.
A closed star alias additionally binds a unique literal export inventory. Frozen
stdlib source is accepted only when the actual stdlib side file matches the
captured bytes and compiling it matches the native loader code, including typed
constants and nested code metadata, under the collector interpreter optimization.
No provider code is executed; missing or changed source remains UNKNOWN.

V4 symbols may carry `contextmanager_signature`: source factory, effective
wrapper/payload, own function evidence, provider support and closed CPython
partial/ABC witnesses. Strict decoding binds this metadata to its carrying function,
original return, runtime and supported provider roles. Tags become owned enums;
wire spellings and original signature fields remain unchanged. Earlier protocols
reject this metadata. Unsupported source transformations remain UNKNOWN.

V5 keeps the V4 collection envelope and facts, but encodes source records and evidence
as canonical positional rows with a sorted data-field table and lossless repeated-string
references. V1–V4 retain their original wire formats.

V6 wraps the same bare V1 positional rows in a `source-facts-columnar-v2` envelope. It
interns JSON object keys in a sorted unique `key_table` and string values in a sorted unique
`string_table`; canonical decimal object keys index the former and `$<index>` value
references index the latter. The decoder checks canonical tables and references, expands
both pools and the V1 rows, then applies the unchanged strict SourceFacts validator. V6
requests retain the V4/V5 provider-source and phase fields, and V6 responses retain the
ordinary provider-sources field. V1–V5 wire behavior is unchanged. See
[AD-253](decisions/ad-253-source-facts-columnar-key-and-value-pooling.md).

V7 keeps the V6 wire and adds the request `features` list: a Python collector collects only
the base resolution families plus the requested gated ones and declares them in
`capabilities.resolution_features`. Records of a family a pre-V7 collector cannot name are
dropped on decode.

V8 ("plain") keeps the V7 request and the V7 semantics, but its facts are the ordinary fact
objects, without the key and string pools of V6/V7. The response bytes on stdout are
zlib-compressed (level 1); plain JSON starts with `{` and zlib with `0x78`, and only V8
responses may be compressed. The collector output limit applies to the compressed bytes,
and the decompressed size is bounded at 16 times that limit. V1–V7 wire behavior is
unchanged. See [AD-259](decisions/ad-259-one-plain-wire-one-validation.md).

This migration covers the named collector/codec modules. It does not assert that every historical string-controlled branch in the repository has been migrated.

SourceProfile and SourceSectionName are nominal enums decoded at ingress, with exactly the former three profile IDs and eight section names. ObservedSection remains a compatibility name for the shared section identity owner. Its old six-value Literal annotation imposed no runtime validation; only this internal annotation now names the full canonical vocabulary. Registered profile subsets and mandatory imports/unknowns validation remain unchanged and have decoder controls.

`CollectionErrorKind` owns the four local collector failure categories in the protocol module. Process collectors produce these values and the observation adapter consumes them; the category names and diagnostic routing remain unchanged.

The existing binary `model.Verdict` now owns PASS/FAIL as an enum. Observation and delta codecs decode it through one shared parser; UNKNOWN remains invalid for coverage and is reserved for rule assessments. No second codec-specific verdict vocabulary is introduced.
