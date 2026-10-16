# TypeScript source inputs

The shared `source_input` port owns recognized filename suffixes, source categories, loading-format hints, extension substitution/selection order, path tokens and reserved module-specifier syntax. Configuration owns snapshot I/O and compiler options; resolution owns package lookup and manifest decisions; collection owns published facts; parsing owns Tree-sitter grammar.

`FileSuffix.NONE` means no suffix. `classify_file` returns `None` for an unsupported suffix; it never assigns that input a known source category or default suffix. `FileParts` contains only a known nominal suffix. Compound declarations win before ordinary suffixes; case and dotfile behavior follow the compiler. JSON-generated declaration suffixes remain output spelling, preserving input recognition of their existing `.ts` ending.

`SpecifierInfo` distinguishes exact dot/dotdot from relative path prefixes, reserved Node/imports/scoped syntax and absolute input. Package names and paths remain open data. Existing Node builtin names are module identities; the scheme-only catalog is unchanged. No mode or parser dispatch is hidden in an open-key API.

Moved `config.PathToken`, `resolve.SourceKind`, `resolve.ModuleFormat` and `resolve.Format` retain identity reexports. Snapshot roles use the existing IR `ResolutionRole`; valid legacy role values normalize at the read boundary. Source/format/role wire spellings and lookup order remain unchanged. The parser retains its conservative TSX fallback for unrecognized filenames and its old final-newline regex behavior.

The authored Target pins actual nominal decoder returns and DTO fields. Whole-module native construct guards retain their exact source scope and no allowances. Actual-source mutations must fail those guards and the fixed Target. TypeScript source input migration addresses twenty measured prefix/suffix findings; the independent Dart findings remain a separate step. This does not claim runtime type checking or new resolution authority.
