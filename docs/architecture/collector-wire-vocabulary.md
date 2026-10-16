# Typed collector wire boundaries

Source facts own Language, RuntimeRequirementState, member inventory vocabulary and input roles. Runtime and Core ports explicitly reexport the same Language class. Protocol owns supported collector envelope versions, and resolver variants keep fixed Literal[Language.MEMBER] discriminators.

Codecs convert closed wire tags to private enums, then construct existing nominal ImportTarget and TypeShape variants. Runtime requirement states use one shared validator. Observation decoding consumes the profile's typed optional-section and unmeasured-scalar capabilities. Profile identity never selects coverage behavior.

JSON and TOML field labels remain declarative schema data validated by the existing exact-structure boundary. Module names, paths, source text and open profile-owned Record.kind values remain data. Path parser tokens, version gates, wire discriminators and columnar string sentinels are closed control vocabulary.

The existing v1/v2/v3 collector encodings, strict version rejection, old observation encodings and source dirty unknown spelling remain stable. Native tests observe actual codec source, reject equality, membership, match and Final-string controls, and weaken the real protocol-version annotation against unchanged authored Target intent.

This migration covers the named collector/codec modules. It does not assert that every historical string-controlled branch in the repository has been migrated.

SourceProfile and SourceSectionName are nominal enums decoded at ingress, with exactly the former three profile IDs and eight section names. ObservedSection remains a compatibility name for the shared section identity owner. Its old six-value Literal annotation imposed no runtime validation; only this internal annotation now names the full canonical vocabulary. Registered profile subsets and mandatory imports/unknowns validation remain unchanged and have decoder controls.

`CollectionErrorKind` owns the four local collector failure categories in the protocol module. Process collectors produce these values and the observation adapter consumes them; the category names and diagnostic routing remain unchanged.

The existing binary `model.Verdict` now owns PASS/FAIL as an enum. Observation and delta codecs decode it through one shared parser; UNKNOWN remains invalid for coverage and is reserved for rule assessments. No second codec-specific verdict vocabulary is introduced.
