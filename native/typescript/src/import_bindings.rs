// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The local names that one import statement binds (`_import_bindings`).

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::members::{children, Cx};
use crate::syntax::Span;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ImportBinding {
    pub span: Span,
    pub imported: String,
    pub local: String,
    pub namespace: bool,
    pub type_only: bool,
    pub source_unique: bool,
}

fn binding(span: &Span, imported: String, local: String, type_only: bool) -> ImportBinding {
    ImportBinding {
        span: span.clone(),
        imported,
        local,
        namespace: false,
        type_only,
        source_unique: false,
    }
}

/// The bindings of one `import_statement`, in the order of the default, named and namespace names.
pub fn of_statement(cx: &Cx, statement: Node) -> Vec<ImportBinding> {
    let parts = children(statement);
    let Some(clause) = parts.iter().find(|part| cx.k(**part) == K::ImportClause) else {
        return Vec::new();
    };
    let span = cx.span(statement);
    let statement_type = parts.iter().any(|part| cx.k(*part) == K::Type);
    let inner = children(*clause);
    let mut result = Vec::new();
    if let Some(default) = inner.iter().find(|part| cx.k(**part) == K::Identifier) {
        result.push(binding(
            &span,
            "default".to_owned(),
            cx.text(*default),
            statement_type,
        ));
    }
    if let Some(named) = inner.iter().find(|part| cx.k(**part) == K::NamedImports) {
        for item in children(*named) {
            if cx.k(item) != K::ImportSpecifier {
                continue;
            }
            let imported = cx.field(item, F::Name);
            let local = cx.field(item, F::Alias).or(imported);
            if let (Some(imported), Some(local)) = (imported, local) {
                let type_only = statement_type || cx.has_child(item, K::Type);
                result.push(binding(&span, cx.text(imported), cx.text(local), type_only));
            }
        }
    }
    if let Some(namespace) = inner.iter().find(|part| cx.k(**part) == K::NamespaceImport) {
        if let Some(local) = namespace.named_child(0) {
            let mut item = binding(&span, "*".to_owned(), cx.text(local), statement_type);
            item.namespace = true;
            result.push(item);
        }
    }
    result
}
