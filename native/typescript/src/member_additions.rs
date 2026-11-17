// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The forms of a file that can give a class, an interface or an enum a member that its body does
//! not show (AD-747). The member inventory of such a classifier is `partial`.
//!
//! The members of a classifier are those that `tsc` gives its type. Its body shows all of them
//! unless one of these forms merges more into the type:
//!
//! - the file is no TypeScript module: a script declares its names in the global scope, where any
//!   other script or declaration file can merge an interface into them; in a JavaScript file
//!   `tsc` also reads the writes `this.x = ...` as members;
//! - a namespace of the same name in the file merges its exports into the classifier.
//!
//! A module augmentation (`declare module "./x"`) is a coverage gap of its file (`concerns.rs`),
//! so the run that it is in is not complete. A class decorator, a prototype write and
//! `Object.assign` change the object at run time, not the type. The collector still keeps the
//! direct forms of these writes and a base that is no name `partial` (`Additions::patched`): it
//! is stricter than the type, never weaker.

use std::collections::BTreeSet;

use tree_sitter::Node;

use crate::ancestors::Entry;
use crate::definitions::{Definition, DefinitionKind};
use crate::kinds::{F, K};
use crate::tree::cx::Cx;
use crate::tree::nodes::named_children;

/// Why the declaration space of a classifier is open: a script or JavaScript file.
pub(crate) const NO_MODULE: &str =
    "the file is no TypeScript module: another file can merge a member into its declarations";
/// Why the declaration space of a classifier is open: a namespace of its name.
pub(crate) const NAMESPACE: &str = "a namespace of the same name merges members into it";
/// Why a class can have a member that its body does not show: a write of its members.
pub(crate) const PATCHED: &str =
    "a prototype write, an Object or Reflect call or a base that is no name can add a member";

/// The forms of one file that can add a member to a classifier.
#[derive(Default)]
pub(crate) struct Additions {
    /// The names of the classes whose members the file can change: `N.prototype`, the first
    /// argument `N` or `this` of an `Object` or `Reflect` call, and a base that is no name. A
    /// name stands for every class of that name in the project.
    pub(crate) patched: BTreeSet<String>,
    /// The names of the namespaces of the file.
    namespaces: BTreeSet<String>,
}

impl Additions {
    /// Read one named node of the walk; `stack` holds its ancestors.
    pub(crate) fn visit(&mut self, cx: &Cx, node: Node, kind: K, stack: &[Entry]) {
        match kind {
            K::InternalModule | K::Module => {
                let name = cx.field(node, F::Name);
                if let Some(name) = name.filter(|name| cx.k(*name) != K::String) {
                    let text = cx.text(name);
                    let first = text.split('.').next().unwrap_or_default().trim();
                    self.namespaces.insert(first.to_owned());
                }
            }
            K::MemberExpression => {
                let property = cx.field(node, F::Property).map(|item| cx.text(item));
                if property.as_deref() == Some("prototype") {
                    self.patched
                        .extend(identifier(cx, cx.field(node, F::Object)));
                }
            }
            K::SubscriptExpression => {
                let index = cx.field(node, F::Index).map(|item| cx.text(item));
                let quotes: &[char] = &['"', '\'', '`'];
                if index.is_some_and(|text| text.trim_matches(quotes) == "prototype") {
                    self.patched
                        .extend(identifier(cx, cx.field(node, F::Object)));
                }
            }
            K::CallExpression => self.reflective(cx, node, stack),
            K::ExtendsClause => {
                let value = cx.field(node, F::Value).map(|item| cx.k(item));
                if !matches!(value, Some(K::Identifier | K::MemberExpression)) {
                    self.patched.extend(enclosing_class(cx, stack));
                }
            }
            _ => {}
        }
    }

    /// `Object.f(N, ...)` or `Reflect.f(N, ...)`: the first argument can get members.
    fn reflective(&mut self, cx: &Cx, node: Node, stack: &[Entry]) {
        let Some(callee) = cx.field(node, F::Function) else {
            return;
        };
        let object = (cx.k(callee) == K::MemberExpression)
            .then(|| cx.field(callee, F::Object))
            .flatten()
            .filter(|object| cx.k(*object) == K::Identifier)
            .map(|object| cx.text(object));
        if !matches!(object.as_deref(), Some("Object" | "Reflect")) {
            return;
        }
        let first = cx
            .field(node, F::Arguments)
            .and_then(|arguments| named_children(arguments).into_iter().next());
        match first.map(|item| (cx.k(item), item)) {
            Some((K::This, _)) => self.patched.extend(enclosing_class(cx, stack)),
            Some((K::Identifier, item)) => {
                self.patched.insert(cx.text(item));
            }
            _ => {}
        }
    }

    /// Mark each classifier of the file whose declaration space is open. `module` is true for a
    /// TypeScript module file.
    pub(crate) fn close(&self, definitions: &mut [Definition], module: bool) {
        for definition in definitions.iter_mut() {
            let classifier = matches!(
                definition.kind,
                DefinitionKind::Class | DefinitionKind::Interface | DefinitionKind::Enum
            );
            if !classifier {
                continue;
            }
            if !module {
                definition.open_scope = Some(NO_MODULE);
            } else if self.namespaces.contains(&definition.name) {
                definition.open_scope = Some(NAMESPACE);
            }
        }
    }
}

fn identifier(cx: &Cx, node: Option<Node>) -> Option<String> {
    node.filter(|node| cx.k(*node) == K::Identifier)
        .map(|node| cx.text(node))
}

/// The name of the innermost class around the node: `this` there is an instance of it.
fn enclosing_class(cx: &Cx, stack: &[Entry]) -> Option<String> {
    let class = stack.iter().rev().find(|entry| {
        matches!(
            entry.kind,
            K::ClassDeclaration | K::AbstractClassDeclaration | K::Class
        )
    })?;
    cx.field(class.node, F::Name).map(|name| cx.text(name))
}
