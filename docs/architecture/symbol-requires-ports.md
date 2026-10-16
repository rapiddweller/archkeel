# Exact symbol ports in required dependencies

Issue #564 extends the module-only restriction documented by AD-42. A `through` entry `sample.core:Command` permits that actual imported name from exactly that module. It does not permit another name, a sibling module, or a whole-module import. Existing module-prefix and empty-through permissions retain their behavior. The provider still owns publication through interface_boundary.

The existing requires_covers API keeps its target-only and module queries; its optional fourth parameter supplies the actual name. requires_import_assessment owns the evidence-sensitive decision, using canonical AssessmentStatus. Violations and UNKNOWN records share this same decision. The wildcard grammar marker belongs to the existing dependency owner and is recognized once when reading raw import facts; arbitrary module and symbol identities remain string data.

Python currently records a wildcard as symbol `*`, even with literal __all__; those records do not prove individual imported names. They stay UNKNOWN when an exact symbol is needed. An import from another module is still definitively forbidden. A plain module-prefix permission can decide such imports without name evidence. No new collector authority or wildcard expansion is introduced.
