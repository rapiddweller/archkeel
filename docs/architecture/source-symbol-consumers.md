# Source symbol consumers

Facts owns SourceSymbolKind and its optional scalar reader. Source collectors translate their own parser domains at publication; SourceFacts consumers decode the selected known tag without closing Record.kind or changing future extension data.

Outer record kind, mirrored symbol_category and indexed record_kind have distinct roles. In particular Dart typedefs remain outer alias records with type_alias metadata; graph enum literals remain EntityKind values. A present null category never acquires the absent-field fallback.

Actual consumer guards protect public API position selection, unreferenced class selection and Python ancestry propagation. Native mutations insert raw source-tag dispatch into these actual functions and must fail fixed authored intent. Existing source-validation, collector, boundary and graph tests retain behavior and error contracts.
