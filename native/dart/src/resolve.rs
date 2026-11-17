// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Dart name resolver (AD-796): the namespace of each library, read from the syntax of the
//! library and its parts and from its `import` and `export` directives. It ports the namespace
//! part of release 4.0.1 `analyzer/dart/resolve.py`, and it reads only facts that the survey
//! proved: a module is a library of the survey or the owner of a part (`import_survey/parts.rs`).
//!
//! The resolver reads programs that `dart analyze` accepts, as the other collectors read code
//! that their compiler accepts (AD-608). It uses that basis in two places:
//!
//! - a name that a library declares hides an imported name of the same name;
//! - a name that a project library exports through an unprefixed import is the binding of that
//!   name, even when an import of another package is unread: two non-platform libraries that
//!   export one used name are a compile error, and a `dart:` library loses to a project library.
//!
//! A name of a library outside the snapshot has no binding here, so it stays unresolved.

mod answers;
mod formals;
mod namespace;
mod params;
pub(crate) mod types;

use std::collections::BTreeMap;

use crate::import_survey::index::{Index, Kind, Owners};
use crate::import_survey::uri::{classify, Uri};
use crate::syntax::{Definition, DefinitionKind, Directive, DirectiveKind, Span, Syntax};

/// One top-level declaration of a module, in the file that writes it.
#[derive(Clone, Copy)]
pub(crate) struct Decl<'a> {
    /// The source index of the file.
    pub(crate) at: usize,
    pub(crate) module: &'a str,
    pub(crate) definition: &'a Definition,
}

/// One resolved URI of a directive (`ResolvedTarget`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Target {
    pub(crate) module: String,
    pub(crate) package: String,
    /// The source index of a selected local library.
    pub(crate) at: Option<usize>,
    pub(crate) uri: String,
    pub(crate) builtin: bool,
}

/// A declaration that a name binds (`ResolvedBinding`).
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct Bound {
    pub(crate) at: usize,
    pub(crate) span: Span,
    pub(crate) module: String,
    pub(crate) name: String,
    pub(crate) kind: DefinitionKind,
    pub(crate) via_prefix: Option<String>,
    pub(crate) id: String,
}

/// The type arguments of a class for its type parameters, in the order of the parameters.
pub(crate) type Substitutions = Vec<(String, String)>;

/// The kinds of a declaration that can be the type of a construction or a receiver.
pub(crate) fn class_like(kind: DefinitionKind) -> bool {
    matches!(
        kind,
        DefinitionKind::Class
            | DefinitionKind::Interface
            | DefinitionKind::Enum
            | DefinitionKind::Mixin
    )
}

/// The word of a closed syntax value, as the Python `StrEnum` writes it.
pub(crate) fn word<T: serde::Serialize>(value: &T) -> String {
    serde_json::to_value(value)
        .ok()
        .and_then(|value| serde_json::Value::as_str(&value).map(str::to_owned))
        .unwrap_or_default()
}

/// The namespaces of the libraries of one survey.
pub(crate) struct Resolver<'a> {
    pub(crate) index: &'a Index<'a>,
    /// The full syntax of each source, by source index; `None` without a module.
    pub(crate) syntax: &'a [Option<Syntax>],
    modules: Vec<Option<&'a str>>,
    definitions: BTreeMap<&'a str, Vec<Decl<'a>>>,
    imports: BTreeMap<&'a str, Vec<(usize, &'a Directive)>>,
    exports: BTreeMap<&'a str, Vec<(usize, &'a Directive)>>,
}

impl<'a> Resolver<'a> {
    /// The resolver of the sources of `index`; `syntax` holds the full parse of each of them.
    pub(crate) fn new(index: &'a Index<'a>, owners: &Owners, syntax: &'a [Option<Syntax>]) -> Self {
        let modules: Vec<Option<&'a str>> = index
            .kinds
            .iter()
            .enumerate()
            .map(|(at, kind)| match kind {
                Kind::Library => Some(String::as_str(&index.sources[at].module)),
                Kind::Part => owners
                    .get(&at)
                    .map(|library| String::as_str(&index.sources[*library].module)),
                Kind::Unknown => None,
            })
            .collect();
        let mut definitions: BTreeMap<&str, Vec<Decl<'_>>> = BTreeMap::new();
        let mut imports: BTreeMap<&str, Vec<(usize, &Directive)>> = BTreeMap::new();
        let mut exports: BTreeMap<&str, Vec<(usize, &Directive)>> = BTreeMap::new();
        for (at, module) in modules.iter().enumerate() {
            let (Some(module), Some(Some(parsed))) = (module, syntax.get(at)) else {
                continue;
            };
            for definition in &parsed.definitions {
                definitions.entry(module).or_default().push(Decl {
                    at,
                    module,
                    definition,
                });
            }
            let of = |kind: DirectiveKind| {
                parsed
                    .directives
                    .iter()
                    .filter(move |item| item.kind == kind)
            };
            imports
                .entry(module)
                .or_default()
                .extend(of(DirectiveKind::Import).map(|item| (at, item)));
            exports
                .entry(module)
                .or_default()
                .extend(of(DirectiveKind::Export).map(|item| (at, item)));
        }
        Self {
            index,
            syntax,
            modules,
            definitions,
            imports,
            exports,
        }
    }

    /// The module of the source at `at`: its library, or the library of a part.
    pub(crate) fn module_for(&self, at: usize) -> Option<&'a str> {
        self.modules.get(at).copied().flatten()
    }

    /// The path of the source at `at`.
    pub(crate) fn rel(&self, at: usize) -> &'a str {
        String::as_str(&self.index.sources[at].rel_path)
    }

    /// The identity of a declaration (`_Declaration.identity`).
    pub(crate) fn identity(&self, decl: &Decl<'_>) -> String {
        let definition = decl.definition;
        format!(
            "{}:{}:{}:{}",
            self.rel(decl.at),
            definition.span.start_byte,
            word(&definition.kind),
            definition.name
        )
    }

    /// The declarations of `module` named `name` (`_local_declarations`).
    pub(crate) fn local(&self, module: &str, name: &str) -> Vec<Decl<'a>> {
        self.definitions
            .get(module)
            .into_iter()
            .flatten()
            .filter(|decl| decl.definition.name == name)
            .copied()
            .collect()
    }

    /// The declaration of `definition` in the file at `at` (`_declaration_for`).
    pub(crate) fn declaration(&self, at: usize, definition: &Definition) -> Option<Decl<'a>> {
        let module = self.module_for(at)?;
        self.definitions.get(module)?.iter().copied().find(|decl| {
            decl.at == at && decl.definition.span.start_byte == definition.span.start_byte
        })
    }

    /// The declaration with the identity `id` in `module`.
    pub(crate) fn by_identity(&self, module: &str, id: &str) -> Option<Decl<'a>> {
        self.definitions
            .get(module)?
            .iter()
            .copied()
            .find(|decl| self.identity(decl) == id)
    }

    /// The binding of a declaration (`_binding`).
    pub(crate) fn bound(&self, decl: &Decl<'_>, prefix: Option<&str>) -> Bound {
        Bound {
            module: decl.module.to_owned(),
            name: decl.definition.name.clone(),
            kind: decl.definition.kind,
            via_prefix: prefix.map(str::to_owned),
            id: self.identity(decl),
            at: decl.at,
            span: decl.definition.span.clone(),
        }
    }

    /// The targets of each URI of `directive` in the file at `at`, without a repeat
    /// (`resolve_directive`). A part, an unselected file and a URI that the survey does not read
    /// give no target: the survey already named each of them as a gap.
    pub(crate) fn targets(&self, at: usize, directive: &Directive) -> Vec<Target> {
        let importer = self.rel(at);
        let mut uris: Vec<&str> = directive.target.as_deref().into_iter().collect();
        for (_, alternative) in &directive.alternatives {
            if !uris.contains(&String::as_str(alternative)) {
                uris.push(alternative);
            }
        }
        let mut found: Vec<Target> = Vec::new();
        for target in uris
            .into_iter()
            .filter_map(|uri| self.target(importer, uri))
        {
            if !found
                .iter()
                .any(|item| item.module == target.module && item.at == target.at)
            {
                found.push(target);
            }
        }
        found
    }

    /// The target of one URI of a directive in the file `importer`.
    fn target(&self, importer: &str, uri: &str) -> Option<Target> {
        let (module, package, at, builtin) = match classify(importer, uri, self.index.package) {
            Uri::Builtin(module) => (module, "dart".to_owned(), None, true),
            Uri::External { package, module } => (module, package, None, false),
            Uri::Local(rel) => {
                let target = *self.index.by_rel.get(String::as_str(&rel))?;
                if self.index.kinds[target] != Kind::Library {
                    return None;
                }
                let module = self.index.sources[target].module.clone();
                (module, self.index.package.to_owned(), Some(target), false)
            }
            Uri::Outside | Uri::Unsupported(_) => return None,
        };
        Some(Target {
            module,
            package,
            at,
            uri: uri.to_owned(),
            builtin,
        })
    }
}

#[cfg(test)]
#[path = "resolve_tests.rs"]
mod tests;
