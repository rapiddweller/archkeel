// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Definitions: classes, interfaces, enumerations, functions, methods, type aliases and constants.
//!
//! The walk offers each node here. `_inner` and `_variables` of `parse.py` run two walks of their
//! own; here one visit of a node does the work of both, with the ancestors from the walk stack.

use std::collections::HashSet;

use tree_sitter::Node;

use crate::exports::ModuleExports;
use crate::kinds::{F, K};
use crate::members::{
    children, has_backslash, named_children, Base, Cx, Member, Parameter, Place, Visibility,
};
use crate::syntax::Span;
use crate::walk::{Entry, ERROR_ABOVE, INSIDE_NAMESPACE, IN_FUNCTION_LIKE, IN_UNMODELED_BLOCK};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DefinitionKind {
    Class,
    Interface,
    Enum,
    Method,
    Function,
    TypeAlias,
    Constant,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Definition {
    pub name: String,
    pub kind: DefinitionKind,
    pub span: Span,
    /// The scope of the parent definition: its qualified name is `Scopes::qualified`.
    pub parent: Option<u32>,
    pub visibility: Option<Visibility>,
    pub is_static: bool,
    pub exported: bool,
    pub annotation: Option<String>,
    pub parameters: Vec<Parameter>,
    pub returns: Option<String>,
    pub bases: Vec<Base>,
    pub members: Vec<Member>,
    pub decorators: bool,
    pub is_abstract: bool,
    pub members_complete: bool,
    pub overload_signature: bool,
    pub top_level: bool,
    pub signature_complete: bool,
    pub parent_line: Option<i64>,
    pub parent_column: Option<i64>,
    pub is_async: bool,
    pub decorator_sources: Vec<(String, Span)>,
}

/// A definition that other definitions can nest in. The qualified name is the chain of the names
/// from the root scope, so a scope costs one name and not a copy of the whole chain.
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct Scope {
    name: String,
    parent: Option<u32>,
    line: i64,
    column: i64,
}

/// The scopes of one file, in the order of their definitions.
#[derive(Default)]
pub struct Scopes(Vec<Scope>);

impl Scopes {
    /// `parent_name` of Python: `parent.name` joined with a dot, from the outermost scope in.
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub fn qualified(&self, at: u32) -> String {
        let mut names = Vec::new();
        let mut next = Some(at);
        while let Some(index) = next {
            let Some(scope) = self.0.get(index as usize) else {
                break;
            };
            names.push(scope.name.as_str());
            next = scope.parent;
        }
        names.reverse();
        names.join(".")
    }
}

#[derive(Default)]
pub struct Defs {
    /// The definitions of the first walk (`_inner`).
    found: Vec<Definition>,
    scopes: Scopes,
    /// The constants (`_variables`), before the filter for module arrays.
    constants: Vec<Definition>,
    array_spans: Vec<Span>,
    /// Module names that an array constant must not shadow.
    omitted: HashSet<String>,
    opaque: bool,
}

fn definition_kind(kind: K) -> Option<DefinitionKind> {
    Some(match kind {
        K::ClassDeclaration => DefinitionKind::Class,
        K::InterfaceDeclaration => DefinitionKind::Interface,
        K::EnumDeclaration => DefinitionKind::Enum,
        K::FunctionDeclaration | K::FunctionSignature => DefinitionKind::Function,
        K::MethodDefinition | K::MethodSignature => DefinitionKind::Method,
        K::TypeAliasDeclaration => DefinitionKind::TypeAlias,
        _ => return None,
    })
}

/// The kind of the ancestor `up` levels above the node: 1 is the parent.
fn ancestor_kind(stack: &[Entry], up: usize) -> Option<K> {
    stack.len().checked_sub(up).map(|at| stack[at].kind)
}

/// The place of the node that the walk visits: its parent, its grandparent and the run of
/// decorators and comments before it.
fn place_of<'a, 't>(stack: &'a [Entry<'t>]) -> Place<'a, 't> {
    let parent = stack.last();
    Place {
        parent: parent.map(|entry| entry.node),
        parent_kind: parent.map_or(K::Other, |entry| entry.kind),
        grand_kind: ancestor_kind(stack, 2).unwrap_or(K::Other),
        before: parent.map_or(&[], |entry| entry.run.as_slice()),
    }
}

/// A declaration that sits at the top of the file, or in an `export` at the top of the file.
fn top_of_file(stack: &[Entry], up: usize) -> bool {
    match ancestor_kind(stack, up) {
        Some(K::Program) => true,
        Some(K::ExportStatement) => ancestor_kind(stack, up + 1) == Some(K::Program),
        _ => false,
    }
}

impl Defs {
    /// `_inner`: record `node` when it is a definition. Returns the scope that it opens.
    pub fn definition(
        &mut self,
        cx: &Cx,
        node: Node,
        kind: K,
        stack: &[Entry],
        seen: u8,
    ) -> Option<u32> {
        let found = definition_kind(kind)?;
        if node.has_error() || seen & (ERROR_ABOVE | INSIDE_NAMESPACE | IN_UNMODELED_BLOCK) != 0 {
            return None;
        }
        let place = place_of(stack);
        let name_node = cx.field(node, F::Name);
        let mut name = name_node.map_or_else(String::new, |name| cx.text(name));
        if cx.supported_constructor(node, &place) {
            name = "constructor".to_owned();
        }
        let name_node = name_node?;
        if name.is_empty() || matches!(cx.k(name_node), K::Other | K::ComputedPropertyName) {
            return None;
        }
        if matches!(kind, K::MethodDefinition | K::MethodSignature) && !place.class_member() {
            return None;
        }
        let owner = stack.last().and_then(|entry| entry.scope);
        let parent = owner.and_then(|at| self.scopes.0.get(at as usize).map(|scope| (at, scope)));
        let definition = Self::build(cx, node, (name.clone(), found), parent, (stack, &place));
        self.scopes.0.push(Scope {
            name,
            parent: owner,
            line: definition.span.line,
            column: definition.span.column,
        });
        self.found.push(definition);
        Some((self.scopes.0.len() - 1) as u32)
    }

    /// `_definition`.
    fn build(
        cx: &Cx,
        node: Node,
        (name, kind): (String, DefinitionKind),
        parent: Option<(u32, &Scope)>,
        (stack, place): (&[Entry], &Place),
    ) -> Definition {
        let owner = cx.k(node);
        let body = cx.field(node, F::Body);
        let nested = matches!(
            kind,
            DefinitionKind::Class | DefinitionKind::Interface | DefinitionKind::Enum
        ) && body.is_some();
        let (members, bases) = match body {
            Some(body) if nested => (cx.declared_members(body, owner), cx.bases(node)),
            _ => (Vec::new(), Vec::new()),
        };
        let kids = children(node);
        let modifiers = cx.modifiers_in(&kids);
        let decorator_sources = cx.decorator_sources_in(node, &kids, place);
        Definition {
            name,
            kind,
            span: cx.span(node),
            parent: parent.map(|(at, _)| at),
            visibility: cx.visibility_in(node, &kids),
            is_static: modifiers.has_static(),
            exported: ancestor_kind(stack, 1) == Some(K::ExportStatement),
            annotation: cx.type_text(cx.field(node, F::Type).or_else(|| cx.field(node, F::Value))),
            parameters: cx.parameters(cx.field(node, F::Parameters)),
            returns: cx.type_text(cx.field(node, F::ReturnType)),
            bases,
            members,
            decorators: !decorator_sources.is_empty(),
            is_abstract: modifiers.has_abstract(),
            members_complete: cx.members_complete(body, owner),
            overload_signature: body.is_none(),
            top_level: top_of_file(stack, 1),
            signature_complete: cx.signature_complete(node),
            parent_line: parent.map(|(_, scope)| scope.line),
            parent_column: parent.map(|(_, scope)| scope.column),
            is_async: kids.iter().any(|child| cx.k(*child) == K::Async),
            decorator_sources,
        }
    }

    /// `_variables` and `_uncollected_module_binding` for one node.
    pub fn variable(&mut self, cx: &Cx, node: Node, kind: K, stack: &[Entry], seen: u8) {
        let (peer, opaque) = uncollected(cx, node, kind, stack, seen);
        self.omitted.extend(peer);
        self.opaque |= opaque;
        if kind != K::VariableDeclarator {
            return;
        }
        let module_level = top_of_file(stack, 2);
        let name_node = cx.field(node, F::Name);
        let Some(name_node) = name_node.filter(|name| cx.k(*name) == K::Identifier) else {
            self.opaque |= module_level;
            return;
        };
        let name = cx.text(name_node);
        self.opaque |= module_level && (name.is_empty() || has_backslash(&name));
        let value = cx.field(node, F::Value);
        let declaration = stack
            .last()
            .filter(|entry| entry.kind == K::LexicalDeclaration);
        let kind_node = declaration.and_then(|entry| cx.field(entry.node, F::Kind));
        let is_array =
            value.is_some_and(|value| module_array_constant(cx, node, value, stack, seen));
        let plain = value.is_some_and(|value| {
            matches!(
                cx.k(value),
                K::Identifier | K::String | K::Number | K::True | K::False | K::Null
            )
        });
        if !kind_node.is_some_and(|kind| cx.k(kind) == K::Const) || !(plain || is_array) {
            if module_level {
                self.omitted.insert(name);
            }
            return;
        }
        let owner = stack.last().and_then(|entry| entry.scope);
        let owner = owner.and_then(|at| self.scopes.0.get(at as usize).map(|scope| (at, scope)));
        let constant = Definition {
            name,
            kind: DefinitionKind::Constant,
            span: cx.span(node),
            parent: owner.map(|(at, _)| at),
            visibility: None,
            is_static: false,
            exported: ancestor_kind(stack, 2) == Some(K::ExportStatement),
            annotation: cx.type_text(cx.field(node, F::Type)),
            parameters: Vec::new(),
            returns: None,
            bases: Vec::new(),
            members: Vec::new(),
            decorators: false,
            is_abstract: false,
            members_complete: true,
            overload_signature: false,
            top_level: module_level,
            signature_complete: true,
            parent_line: owner.map(|(_, scope)| scope.line),
            parent_column: owner.map(|(_, scope)| scope.column),
            is_async: false,
            decorator_sources: Vec::new(),
        };
        if is_array {
            self.array_spans.push(constant.span.clone());
        }
        self.constants.push(constant);
    }

    /// The definitions in file order after the filter for module arrays and the module visibility.
    pub fn finish(
        mut self,
        imported: &HashSet<String>,
        exports: &ModuleExports,
    ) -> (Vec<Definition>, Scopes) {
        let opaque = self.opaque || imported.iter().any(|name| has_backslash(name));
        self.omitted.extend(imported.iter().cloned());
        let kept = self.constants.into_iter().filter(|item| {
            !self.array_spans.contains(&item.span)
                || (!opaque && !self.omitted.contains(&item.name))
        });
        let mut all: Vec<Definition> = self.found.into_iter().chain(kept).collect();
        for item in &mut all {
            module_visibility(item, exports);
        }
        all.sort_by_key(|item| (item.span.line, item.span.column));
        (all, self.scopes)
    }
}

/// `_module_visibility`.
fn module_visibility(item: &mut Definition, exports: &ModuleExports) {
    if !item.top_level {
        return;
    }
    let exported = item.exported || exports.exported.contains(&item.name);
    let visible = item.exported || exports.visible.contains(&item.name);
    item.exported = exported;
    let certain = exports.module_syntax && exports.complete;
    if !visible && !certain {
        return;
    }
    if item.visibility.is_none() {
        item.visibility = Some(if visible {
            Visibility::Public
        } else {
            Visibility::Private
        });
    }
}

/// `_module_array_constant`: a direct module declaration of an array of plain values.
fn module_array_constant(cx: &Cx, node: Node, value: Node, stack: &[Entry], seen: u8) -> bool {
    if node.has_error() || seen & ERROR_ABOVE != 0 || !top_of_file(stack, 2) {
        return false;
    }
    let mut value = value;
    if cx.k(value) == K::AsExpression {
        let parts: Vec<Node> = crate::members::children(value)
            .into_iter()
            .filter(|item| cx.k(*item) != K::Comment)
            .collect();
        if parts.len() != 3 || cx.k(parts[1]) != K::As || cx.k(parts[2]) != K::Const {
            return false;
        }
        value = parts[0];
    }
    cx.k(value) == K::Array
        && named_children(value).into_iter().all(|item| {
            matches!(
                cx.k(item),
                K::Identifier | K::String | K::Number | K::True | K::False | K::Null | K::Comment
            )
        })
}

/// A name or an opaque binding: `(name, opaque)`.
type Peer = (Option<String>, bool);

fn plain_name(cx: &Cx, binding: Option<Node>, kinds: &[K]) -> Peer {
    let Some(binding) = binding.filter(|binding| kinds.contains(&cx.k(*binding))) else {
        return (None, true);
    };
    let name = cx.text(binding);
    if name.is_empty() || has_backslash(&name) {
        (None, true)
    } else {
        (Some(name), false)
    }
}

/// `_module_var_array_peer`: a block or loop `var` still competes with a module array.
fn array_peer(cx: &Cx, node: Node, kind: K, stack: &[Entry], seen: u8) -> Peer {
    let variable =
        kind == K::VariableDeclarator && ancestor_kind(stack, 1) == Some(K::VariableDeclaration);
    let looping = kind == K::ForInStatement && cx.has_child(node, K::Var);
    if !(variable || looping) || seen & IN_FUNCTION_LIKE != 0 {
        return (None, false);
    }
    plain_name(cx, node.named_child(0), &[K::Identifier])
}

/// `_uncollected_module_binding`: veto new array identities beside unsupported module syntax.
fn uncollected(cx: &Cx, node: Node, kind: K, stack: &[Entry], seen: u8) -> Peer {
    if !matches!(
        kind,
        K::VariableDeclarator
            | K::ForInStatement
            | K::ClassDeclaration
            | K::FunctionDeclaration
            | K::FunctionSignature
            | K::EnumDeclaration
            | K::ImportAlias
            | K::ImportRequireClause
            | K::InternalModule
            | K::GeneratorFunctionDeclaration
            | K::AbstractClassDeclaration
    ) {
        return (None, false);
    }
    let peer = array_peer(cx, node, kind, stack, seen);
    if peer.0.is_some() || peer.1 {
        return peer;
    }
    let variable = kind == K::VariableDeclarator;
    let defined = matches!(
        kind,
        K::ClassDeclaration | K::FunctionDeclaration | K::FunctionSignature | K::EnumDeclaration
    );
    if !defined && !variable && kind == K::ForInStatement {
        return (None, false);
    }
    let mut up = 1;
    let declaration = if kind == K::ImportRequireClause {
        stack.len().checked_sub(1).map(|at| stack[at].node)
    } else {
        Some(node)
    };
    if variable {
        up = 2;
        if ancestor_kind(stack, up) != Some(K::AmbientDeclaration) {
            return (None, false);
        }
    }
    if kind == K::ImportRequireClause {
        up += 1;
    }
    while matches!(
        ancestor_kind(stack, up),
        Some(K::ExportStatement | K::AmbientDeclaration | K::ExpressionStatement)
    ) {
        up += 1;
    }
    let Some(declaration) = declaration else {
        return (None, false);
    };
    if ancestor_kind(stack, up) != Some(K::Program) || cx.has_child(declaration, K::Type) {
        return (None, false);
    }
    if defined {
        let escaped = named_children(node).into_iter().any(|child| {
            matches!(cx.k(child), K::Identifier | K::TypeIdentifier)
                && has_backslash(&cx.text(child))
        });
        return (None, escaped);
    }
    plain_name(cx, node.named_child(0), &[K::Identifier, K::TypeIdentifier])
}
