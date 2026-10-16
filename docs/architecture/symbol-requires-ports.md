# Exact symbol ports in required dependencies

Issue #564 extends the module-only restriction documented by AD-42. A `through` entry `sample.core:Command` permits that actual imported name from exactly that module. It does not permit another name, a sibling module, or a whole-module import. Existing module-prefix and empty-through permissions retain their behavior. The provider still owns publication through interface_boundary.

The existing requires_covers API keeps its target-only and module queries; its optional fourth parameter supplies the actual name. requires_import_assessment owns the evidence-sensitive decision, using canonical AssessmentStatus. Violations and UNKNOWN records share this same decision. The wildcard grammar marker belongs to the existing dependency owner and is recognized once when reading raw import facts; arbitrary module and symbol identities remain string data.

Python currently records a wildcard as symbol `*`, even with literal __all__; those records do not prove individual imported names. They stay UNKNOWN when an exact symbol is needed. An import from another module is still definitively forbidden. A plain module-prefix permission can decide such imports without name evidence. No new collector authority or wildcard expansion is introduced.

Required selectors are wire string data. The existing parser accepts str subclasses unchanged, so the matcher uses the builtin string primitive to read their actual Unicode content. A native parser/constructor regression proves that an overridden partition method cannot redirect an approved symbol to another namespace; the same sibling remains forbidden.

Import evaluation reads the existing mutable RawRecord.data port, explicitly defined as RawData = dict[str, Any], through classified. It does not consume the immutable RecordData DTO or broaden that port to arbitrary Mapping objects. Missing legacy name fields retain their conservative defaults; false, null, and missing knowledge stay UNKNOWN only when an exact name is necessary. A known whole-module import cannot satisfy an exact name. Native direct-builder controls also preserve the actual stored dictionary contents when an accepted dict subclass overrides get. This primitive lookup adds no symbol-resolution authority.

The source-backed native guard covers the complete dependency module and the selected real matcher declarations in a bounded fixture. Other model controls remain pending under #542; this change does not claim whole-model freedom from string dispatch or add an exception for that remaining work.
