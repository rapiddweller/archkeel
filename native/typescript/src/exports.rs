// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What a module file exports and what a `declare` adds to the global scope.
//!
//! These are the functions `_module_exports`, `_module_export_bindings` and `_ambient_globals` of
//! `parse.py`. They read the statements of the root only, after the walk.

use std::collections::{HashMap, HashSet};

use tree_sitter::Node;

use crate::kinds::K;
use crate::members::{children, named_children, Cx};
use crate::scope::{Frames, ROOT};
use crate::syntax::Span;

/// Names with the span of each.
pub type Named = Vec<(String, Span)>;

/// `_module_exports`: the runtime and visible local exports, and whether they are certain.
pub struct ModuleExports {
    pub module_syntax: bool,
    pub exported: HashSet<String>,
    pub visible: HashSet<String>,
    pub complete: bool,
}

fn is_declaration(kind: K) -> bool {
    matches!(
        kind,
        K::ClassDeclaration
            | K::EnumDeclaration
            | K::FunctionDeclaration
            | K::FunctionSignature
            | K::InterfaceDeclaration
            | K::LexicalDeclaration
            | K::TypeAliasDeclaration
            | K::VariableDeclaration
    )
}

pub fn module_exports(cx: &Cx, root: Node) -> ModuleExports {
    let top = named_children(root);
    let statements: Vec<Node> = top
        .iter()
        .copied()
        .filter(|item| cx.k(*item) == K::ExportStatement)
        .collect();
    let module_syntax = !statements.is_empty()
        || top
            .iter()
            .any(|item| matches!(cx.k(*item), K::ImportStatement | K::ImportAlias));
    let mut found = ModuleExports {
        module_syntax,
        exported: HashSet::new(),
        visible: HashSet::new(),
        complete: true,
    };
    for statement in statements {
        let named = named_children(statement);
        if named.iter().any(|item| is_declaration(cx.k(*item))) {
            continue;
        }
        let clause = named.iter().find(|item| cx.k(**item) == K::ExportClause);
        let has_string = named.iter().any(|item| cx.k(*item) == K::String);
        let Some(clause) = clause else {
            if !has_string {
                found.complete = false;
            }
            continue;
        };
        if has_string {
            continue;
        }
        let statement_is_type_only = cx.has_child(statement, K::Type);
        for specifier in named_children(*clause) {
            if cx.k(specifier) != K::ExportSpecifier {
                continue;
            }
            let name = specifier.child_by_field_name("name");
            let alias = specifier.child_by_field_name("alias");
            let Some(name) =
                name.filter(|name| matches!(cx.k(*name), K::Identifier | K::TypeIdentifier))
            else {
                found.complete = false;
                continue;
            };
            let local = cx.text(name);
            found.visible.insert(local.clone());
            let is_alias = alias.is_some_and(|alias| cx.text(alias) != local);
            let type_only = statement_is_type_only || cx.has_child(specifier, K::Type);
            if !is_alias && !type_only {
                found.exported.insert(local);
            }
        }
    }
    found
}

/// `_module_export_bindings`: `(name, declaration, export)` for a name exported once, declared
/// once and bound once.
pub fn export_bindings(cx: &Cx, root: Node, frames: &Frames) -> Vec<(String, Span, Span)> {
    let top = named_children(root);
    if root.has_error()
        || frames.is_ambiguous(ROOT)
        || top.iter().any(|statement| {
            cx.k(*statement) == K::ExportStatement
                && statement.child_by_field_name("source").is_some()
        })
    {
        return Vec::new();
    }
    let mut declarations: HashMap<String, Vec<Span>> = HashMap::new();
    let mut exports: Vec<(String, Span)> = Vec::new();
    for statement in top {
        let exported = cx.k(statement) == K::ExportStatement;
        let declaration = if exported {
            statement.child_by_field_name("declaration")
        } else {
            Some(statement)
        };
        let direct = exported
            && !children(statement)
                .iter()
                .any(|child| matches!(cx.k(*child), K::Default | K::Type));
        let candidates: Vec<Node> = match declaration {
            Some(declaration)
                if matches!(
                    cx.k(declaration),
                    K::LexicalDeclaration | K::VariableDeclaration
                ) =>
            {
                named_children(declaration)
            }
            Some(declaration) => vec![declaration],
            None => Vec::new(),
        };
        for node in candidates {
            let name = node.child_by_field_name("name");
            let Some(name) = name.filter(|name| {
                matches!(
                    cx.k(node),
                    K::VariableDeclarator | K::FunctionDeclaration | K::ClassDeclaration
                ) && cx.valid_unicode_member_name(*name)
            }) else {
                continue;
            };
            let text = cx.text(name);
            declarations
                .entry(text.clone())
                .or_default()
                .push(cx.span(node));
            if direct {
                exports.push((text, cx.span(statement)));
            }
        }
        if statement.child_by_field_name("source").is_some() {
            continue;
        }
        let clause = if direct {
            children(statement)
                .into_iter()
                .find(|child| cx.k(*child) == K::ExportClause)
        } else {
            None
        };
        for specifier in clause.map(children).unwrap_or_default() {
            if cx.k(specifier) != K::ExportSpecifier {
                continue;
            }
            let name = specifier.child_by_field_name("name");
            let alias = specifier.child_by_field_name("alias");
            if let Some(name) = name {
                if cx.valid_unicode_member_name(name)
                    && alias.is_none()
                    && !cx.has_child(specifier, K::Type)
                {
                    exports.push((cx.text(name), cx.span(specifier)));
                }
            }
        }
    }
    let mut counts: HashMap<&str, usize> = HashMap::new();
    for (name, _) in &exports {
        *counts.entry(name.as_str()).or_default() += 1;
    }
    exports
        .iter()
        .filter(|(name, _)| {
            counts.get(name.as_str()) == Some(&1)
                && declarations.get(name).map(Vec::len) == Some(1)
                && frames.count(ROOT, name) == 1
        })
        .map(|(name, span)| (name.clone(), declarations[name][0].clone(), span.clone()))
        .collect()
}

/// `_declared_names`: the value names that one declaration publishes.
fn declared_names(cx: &Cx, declaration: Node) -> Vec<(String, Span)> {
    // In `declare global { }` a namespace parses as an expression statement; `export` wraps.
    let mut declaration = declaration;
    while matches!(
        cx.k(declaration),
        K::ExpressionStatement | K::ExportStatement
    ) {
        match declaration.named_child(0) {
            Some(inner) => declaration = inner,
            None => return Vec::new(),
        }
    }
    if !matches!(
        cx.k(declaration),
        K::LexicalDeclaration
            | K::VariableDeclaration
            | K::FunctionSignature
            | K::ClassDeclaration
            | K::AbstractClassDeclaration
            | K::EnumDeclaration
            | K::InternalModule
            | K::Module
    ) {
        return Vec::new();
    }
    let names: Vec<Option<Node>> = if matches!(
        cx.k(declaration),
        K::LexicalDeclaration | K::VariableDeclaration
    ) {
        named_children(declaration)
            .into_iter()
            .map(|item| item.child_by_field_name("name"))
            .collect()
    } else {
        vec![declaration.child_by_field_name("name")]
    };
    let mut found = Vec::new();
    for name in names {
        // `namespace A.B.C` publishes `A`; `module "x"` names no global.
        let mut name = name;
        while let Some(node) =
            name.filter(|n| matches!(cx.k(*n), K::NestedIdentifier | K::MemberExpression))
        {
            name = node.named_child(0);
        }
        if let Some(node) = name.filter(|n| matches!(cx.k(*n), K::Identifier | K::TypeIdentifier)) {
            found.push((cx.text(node), cx.span(node)));
        }
    }
    found
}

/// `_ambient_globals`: the names of `declare global { }` blocks, and of the top-level `declare`
/// statements of a file without module syntax.
pub fn ambient(cx: &Cx, root: Node, module_syntax: bool) -> (Named, Named) {
    let mut block = Vec::new();
    let mut top_level = Vec::new();
    for statement in named_children(root) {
        if cx.k(statement) != K::AmbientDeclaration {
            continue;
        }
        let Some(inner) = statement.named_child(0) else {
            continue;
        };
        if cx.k(inner) == K::StatementBlock {
            for declaration in named_children(inner) {
                block.extend(declared_names(cx, declaration));
            }
        } else if !module_syntax {
            top_level.extend(declared_names(cx, inner));
        }
    }
    (block, top_level)
}
