// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one name that a closed UMD declaration envelope publishes, and the names that its factory
//! may write on the global object (`umd_publication`, `_umd_factory_global_writes`,
//! `_umd_global_path`).

use std::collections::{BTreeSet, HashMap};

use tree_sitter::Node;

use crate::definitions::Scopes;
use crate::kinds::{F, K};
use crate::members::{named_children, Cx};
use crate::references::literal;
use crate::script_scope::Tree;
use crate::script_syntax::Producer;
use crate::source::{Source, Span};
use crate::source_input::{classify_file, SourceKind};
use crate::syntax::Parsers;
use crate::umd::Templates;

/// What a closed UMD envelope declares: the name that it publishes, where, and the names that its
/// factory writes on the global object (`None` where the factory may write others).
pub struct Publication {
    pub name: String,
    pub span: Span,
    pub writes: Option<BTreeSet<String>>,
}

/// A scope and a name, with the nodes that declare or write the name in the scope.
type Declared<'t> = HashMap<(usize, String), Vec<Node<'t>>>;

/// The names that an envelope may not use for its factory or its root.
const RESERVED: [&str; 6] = ["exports", "module", "define", "window", "global", "self"];

/// `umd_publication(rel, content)`.
pub fn publication(parsers: &mut Parsers, rel: &str, content: &[u8]) -> Option<Publication> {
    let suffix = classify_file(rel)?;
    if suffix.source_kind() != Some(SourceKind::JavaScript) || suffix.format_hint().is_some() {
        return None;
    }
    let (tree, grammar) = parsers.parse(false, content)?;
    let source = Source::new(content);
    let cx = Cx {
        kinds: &grammar.map,
        source: &source,
    };
    let root = tree.root_node();
    let statements: Vec<Node> = named_children(root)
        .into_iter()
        .filter(|node| cx.k(*node) != K::Comment)
        .collect();
    let [statement] = statements.as_slice() else {
        return None;
    };
    if root.has_error() || cx.k(*statement) != K::ExpressionStatement {
        return None;
    }
    let call = statement.named_child(0)?;
    let wrapper = cx.field(call, F::Function)?;
    let arguments = cx.field(call, F::Arguments)?;
    if cx.k(call) != K::CallExpression || arguments.named_child_count() != 1 {
        return None;
    }
    let factory = arguments.named_child(0)?;
    let parameters = cx.field(factory, F::Parameters)?;
    if cx.k(factory) != K::FunctionExpression
        || parameters.named_child_count() != 0
        || crate::members::children(factory)
            .into_iter()
            .any(|child| cx.k(child) == K::Async)
    {
        return None;
    }
    let captures = grammar.templates.envelope(cx, wrapper)?;
    let (factory_slot, root_slot, publication) =
        (captures.factory?, captures.root?, captures.publication?);
    let valid = [factory_slot, root_slot, publication]
        .into_iter()
        .all(|node| cx.valid_unicode_member_name(node));
    let (factory_name, root_name) = (cx.text(factory_slot), cx.text(root_slot));
    let reserved = |name: &str| RESERVED.contains(&name);
    if !valid || factory_name == root_name || reserved(&factory_name) || reserved(&root_name) {
        return None;
    }
    let writes = factory_writes(cx, root, factory, &grammar.templates);
    Some(Publication {
        name: cx.text(publication),
        span: cx.span(publication),
        writes,
    })
}

/// The kinds that the query `umd_writes` captures as bindings.
fn is_binding(kind: K) -> bool {
    use K::{
        ArrowFunction, CatchClause, Class, ClassDeclaration, ForInStatement, FunctionDeclaration,
        FunctionExpression, GeneratorFunction, GeneratorFunctionDeclaration, MethodDefinition,
        VariableDeclarator, WithStatement,
    };
    matches!(
        kind,
        WithStatement
            | FunctionDeclaration
            | FunctionExpression
            | GeneratorFunctionDeclaration
            | GeneratorFunction
            | ArrowFunction
            | MethodDefinition
            | CatchClause
            | ForInStatement
            | Class
            | ClassDeclaration
            | VariableDeclarator
    )
}

/// The kinds that the query `umd_writes` captures as writes.
fn is_write(kind: K) -> bool {
    matches!(
        kind,
        K::AssignmentExpression
            | K::AugmentedAssignmentExpression
            | K::ForInStatement
            | K::UpdateExpression
            | K::UnaryExpression
    )
}

/// `_umd_factory_global_writes`: the names that the factory writes on the global object, or `None`
/// where it calls a function or writes a name that the file cannot know.
fn factory_writes(
    cx: Cx,
    root: Node,
    factory: Node,
    templates: &Templates,
) -> Option<BTreeSet<String>> {
    let mut tree = Tree::new(cx, root);
    let inside: Vec<Node> = tree.subtree(factory).to_vec();
    if inside
        .iter()
        .any(|node| matches!(cx.k(*node), K::CallExpression | K::NewExpression))
    {
        return None;
    }
    let bindings: Vec<Node> = inside
        .iter()
        .copied()
        .filter(|node| is_binding(cx.k(*node)))
        .collect();
    let writes: Vec<Node> = inside
        .iter()
        .copied()
        .filter(|node| is_write(cx.k(*node)))
        .collect();
    tree.bind(&bindings, &[]);
    let declared = declared_names(&tree, bindings.iter().chain(writes.iter()).copied())?;
    let scopes = Scopes::default();
    let producer = Producer::new(&tree, &[], &scopes, false, templates);
    let mut written = BTreeSet::new();
    for node in writes {
        for target in tree.script_targets(node) {
            if let Some(name) = global_write(&producer, target, factory, &declared)? {
                written.insert(name);
            }
        }
    }
    Some(written)
}

/// The nodes that declare or write each plain name, by the scope that binds it; `None` where a
/// node has a name that cannot be proven.
fn declared_names<'t>(
    tree: &Tree<'_, 't>,
    nodes: impl Iterator<Item = Node<'t>>,
) -> Option<Declared<'t>> {
    let mut declared: Declared = HashMap::new();
    for node in nodes {
        let name = tree.field(node, F::Name);
        if name.is_some_and(|name| !tree.cx.valid_unicode_member_name(name)) {
            return None;
        }
        let binds = matches!(
            tree.k(node),
            K::VariableDeclarator | K::AssignmentExpression
        );
        let name = name.or_else(|| tree.field(node, F::Left)).filter(|_| binds);
        let Some(name) = name.filter(|name| tree.k(*name) == K::Identifier) else {
            continue;
        };
        let spelling = tree.text(name);
        if let Some(scope) = tree.bound_scope(name, &spelling) {
            declared
                .entry((scope.id(), spelling))
                .or_default()
                .push(node);
        }
    }
    Some(declared)
}

/// What one target writes: `Ok(None)` for a write that stays in the factory, a name for a global
/// write, and `None` where the write cannot be known.
fn global_write<'t>(
    producer: &Producer<'_, '_, 't>,
    target: Node<'t>,
    factory: Node<'t>,
    declared: &Declared<'t>,
) -> Option<Option<String>> {
    let tree = producer.tree;
    if tree.k(target) == K::Identifier && tree.bound_scope(target, &tree.text(target)).is_some() {
        return Some(None);
    }
    let Some(path) = global_path(producer, target, factory, declared) else {
        return Some(None);
    };
    if path.len() > 1 {
        return Some(None);
    }
    path.into_iter().next().flatten().map(Some)
}

/// `_umd_global_path`: the path of a target on the global object, where a name that is not known is
/// `None`; `None` where the target has no path.
fn global_path<'t>(
    producer: &Producer<'_, '_, 't>,
    target: Node<'t>,
    factory: Node<'t>,
    declared: &Declared<'t>,
) -> Option<Vec<Option<String>>> {
    let tree = producer.tree;
    let mut receiver = tree.unparenthesized(target);
    let mut suffix: Vec<Option<String>> = Vec::new();
    while matches!(
        tree.k(receiver),
        K::MemberExpression | K::SubscriptExpression
    ) {
        let object = tree.field(receiver, F::Object)?;
        let key = tree.field(receiver, F::Property);
        let name = match key {
            Some(key) => tree
                .cx
                .valid_unicode_member_name(key)
                .then(|| tree.text(key)),
            None => literal(tree.field(receiver, F::Index), tree.cx.source),
        };
        suffix.push(name);
        receiver = tree.unparenthesized(object);
    }
    if suffix.len() > 1 {
        return Some(suffix);
    }
    let path = producer.write_alias_path(receiver, &[], Some(declared), Some(factory))?;
    let named = path.into_iter().map(Some);
    Some(named.chain(suffix.into_iter().rev()).collect())
}
