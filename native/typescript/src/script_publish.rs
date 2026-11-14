// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The publications of a script: an object that it assigns to the global object or returns from a
//! function that it calls once (`_script_assignment_publication`, `_script_return_publication`,
//! `_script_members`).

use std::collections::HashMap;

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_scope::Tree;
use crate::script_syntax::Producer;
use crate::script_types::{DirectPublication, Member, ScriptGlobal};
use crate::tree::nodes::named_children;

/// The `(published name, local name)` pairs and the keys of an object literal.
type Keyed = (Vec<(String, String)>, Vec<String>);

/// The `(published name, local name)` pairs of an object literal, and every key that it writes;
/// `None` for an object that has a member that is not a plain key.
fn object_members<'t>(tree: &Tree<'_, 't>, object: Node<'t>) -> Option<Keyed> {
    let mut members: Vec<(String, String)> = Vec::new();
    let mut keys: Vec<String> = Vec::new();
    for member in named_children(object) {
        match tree.k(member) {
            K::ShorthandPropertyIdentifier => {
                keys.push(tree.text(member));
                members.push((tree.text(member), tree.text(member)));
            }
            K::Pair => {
                let key = tree
                    .field(member, F::Key)
                    .filter(|key| tree.k(*key) == K::PropertyIdentifier)?;
                keys.push(tree.text(key));
                let value = tree
                    .field(member, F::Value)
                    .filter(|value| tree.k(*value) == K::Identifier);
                members.extend(value.map(|value| (tree.text(key), tree.text(value))));
            }
            _ => return None,
        }
    }
    Some((members, keys))
}

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The new witness accepts a closed syntax set, not an incomplete list of dangerous forms.
    pub(crate) fn direct_publications(&self) -> Option<Vec<DirectPublication>> {
        let mut publications = Vec::new();
        for statement in named_children(self.tree.root) {
            self.direct_statement(statement, &mut publications)?;
        }
        Some(publications)
    }

    fn direct_statement(
        &self,
        node: Node<'t>,
        publications: &mut Vec<DirectPublication>,
    ) -> Option<()> {
        let tree = self.tree;
        match tree.k(node) {
            K::Comment => {}
            K::FunctionDeclaration | K::ClassDeclaration => {
                let class = tree.k(node) == K::ClassDeclaration;
                let body = tree.field(node, F::Body)?;
                let name = tree.field(node, F::Name)?;
                let children = named_children(node);
                let empty = named_children(body).is_empty();
                let plain = if class {
                    children.len() == 2
                } else {
                    children.len() == 3
                        && named_children(tree.field(node, F::Parameters)?).is_empty()
                        && !tree.has_child_kind(node, K::Async)
                };
                if !empty || !plain {
                    return None;
                }
                publications.push(DirectPublication {
                    name: tree.text(name), span: tree.span(node), property: !class,
                });
            }
            K::VariableDeclaration | K::LexicalDeclaration => {
                for binding in named_children(node) {
                    let name = tree.field(binding, F::Name)?;
                    let value = tree.field(binding, F::Value);
                    if tree.k(name) != K::Identifier
                        || named_children(binding).len() != 1 + usize::from(value.is_some())
                        || value.is_some_and(|value| !self.primitive(value))
                    {
                        return None;
                    }
                    publications.push(DirectPublication {
                        name: tree.text(name), span: tree.span(binding),
                        property: tree.k(node) == K::VariableDeclaration,
                    });
                }
            }
            K::ExpressionStatement => {
                let children = named_children(node);
                let [expression] = children.as_slice() else { return None; };
                self.direct_expression(*expression, publications)?;
            }
            _ => return None,
        }
        Some(())
    }

    fn primitive(&self, node: Node<'t>) -> bool {
        matches!(self.tree.k(node), K::Number | K::String | K::True | K::False | K::Null)
    }

    fn direct_expression(
        &self,
        node: Node<'t>,
        publications: &mut Vec<DirectPublication>,
    ) -> Option<()> {
        let tree = self.tree;
        match tree.k(node) {
            K::AssignmentExpression => {
                let target = tree.field(node, F::Left)?;
                let path = tree.static_path(target);
                let [host, name] = path.as_slice() else { return None; };
                if !matches!(host.as_str(), "window" | "globalThis" | "self")
                    || !tree.script_free(target, node)
                    || !self.primitive(tree.field(node, F::Right)?)
                {
                    return None;
                }
                publications.push(DirectPublication {
                    name: name.clone(), span: tree.span(node), property: true,
                });
            }
            K::CallExpression => {
                let path = tree.static_path(tree.field(node, F::Function)?);
                if path.is_empty()
                    || path.iter().any(|part| crate::script_writes::is_effect_name(part))
                    || !named_children(tree.field(node, F::Arguments)?).is_empty()
                    || tree.has_child_kind(node, K::OptionalChain)
                {
                    return None;
                }
            }
            _ => return None,
        }
        Some(())
    }

    /// `_script_members`: the functions that an object literal publishes under their own name.
    pub(crate) fn members(&self, object: Node<'t>, wrapper: Option<Node<'t>>) -> Vec<Member> {
        let tree = self.tree;
        let Some((members, keys)) = object_members(tree, object) else {
            return Vec::new();
        };
        let mut counts: HashMap<&str, u32> = HashMap::new();
        for key in &keys {
            let count = counts.entry(key.as_str()).or_insert(0_u32);
            *count = count.saturating_add(1);
        }
        let body = match wrapper {
            Some(wrapper) => tree.field(wrapper, F::Body),
            None => Some(tree.root),
        };
        let mut found = Vec::new();
        for (published, local) in &members {
            if counts.get(published.as_str()) != Some(&1) {
                continue;
            }
            let functions = body.map_or_else(Vec::new, |body| self.functions_named(body, local));
            let at = |declaration: Node<'t>| tree.span(declaration);
            found.extend(
                functions
                    .into_iter()
                    .map(|declaration| (published.clone(), local.clone(), at(declaration))),
            );
        }
        found
    }

    /// Whether the statement of the assignment is a statement of the file or of the wrapper.
    fn direct(&self, node: Node<'t>, wrapper: Option<Node<'t>>) -> bool {
        let tree = self.tree;
        let outer = tree.parent(node).and_then(|parent| tree.parent(parent));
        let body = wrapper.and_then(|wrapper| tree.field(wrapper, F::Body));
        outer.is_some_and(|outer| {
            tree.k(outer) == K::Program || body.is_some_and(|body| body.id() == outer.id())
        })
    }

    /// The receiver of the assignment is the parameter that the wrapper binds to a root, once, and
    /// the wrapper is called with names that are free.
    fn wrapper_receiver_proven(&self, node: Node<'t>, wrapper: Node<'t>, name: &str) -> bool {
        let tree = self.tree;
        let Some(info) = self.wrappers.get(&wrapper.id()) else {
            return false;
        };
        if !info.names.contains(name) {
            return false;
        }
        // The wrapper is the only scope above the node that binds the name: it is the nearest, and
        // none is above it.
        let nearest = tree.bound_scope(node, name);
        let only = nearest.is_some_and(|scope| scope.id() == wrapper.id())
            && tree.bound_scope(wrapper, name).is_none();
        only && tree.count(wrapper, name) == 1
            && !tree.in_ambiguous_scope(node)
            && self.free_arguments(wrapper)
    }

    /// The wrapper is called with names that are free. The arguments are read once for all the
    /// assignments that the wrapper makes.
    fn free_arguments(&self, wrapper: Node<'t>) -> bool {
        let tree = self.tree;
        let call = self.wrappers.get(&wrapper.id()).map(|info| info.call);
        let mut known = self.free_arguments.borrow_mut();
        *known.entry(wrapper.id()).or_insert_with(|| {
            let arguments = call.and_then(|call| tree.field(call, F::Arguments));
            arguments.is_some_and(|arguments| {
                named_children(arguments)
                    .into_iter()
                    .all(|argument| tree.script_free(argument, argument))
            })
        })
    }

    /// `_script_assignment_publication`.
    pub(crate) fn assignment_publication(
        &self,
        node: Node<'t>,
        target: Node<'t>,
        wrapper: Option<Node<'t>>,
    ) -> Option<ScriptGlobal> {
        let tree = self.tree;
        let path = tree.static_path(target);
        let value = tree.field(node, F::Right)?;
        let is_left = tree
            .field(node, F::Left)
            .is_some_and(|left| left.id() == target.id());
        let [receiver, published] = path.as_slice() else {
            return None;
        };
        if tree.k(node) != K::AssignmentExpression || !is_left || tree.k(value) != K::Object {
            return None;
        }
        let direct = self.direct(node, wrapper);
        let proven = tree.script_free(target, node)
            || wrapper.is_some_and(|wrapper| self.wrapper_receiver_proven(node, wrapper, receiver));
        Some(ScriptGlobal {
            name: published.clone(),
            span: tree.span(node),
            members: self.members(value, wrapper),
            stable: direct && proven && self.reaches(node, wrapper),
            source_members: Vec::new(),
            source_origin: direct && proven,
            availability: self
                .prior_returns(node, wrapper)
                .into_iter()
                .map(|item| tree.span(item))
                .collect(),
        })
    }

    /// `_script_return_publication`: `var name = (function () { return {...}; })();`.
    pub(crate) fn return_publication(
        &self,
        node: Node<'t>,
        call: Node<'t>,
    ) -> Option<ScriptGlobal> {
        let tree = self.tree;
        let binding = tree.parent(call)?;
        let declaration = tree.parent(binding)?;
        if tree.k(binding) != K::VariableDeclarator
            || self.module_syntax
            || tree.k(declaration) != K::VariableDeclaration
        {
            return None;
        }
        let name = tree.field(binding, F::Name)?;
        let body = tree.field(node, F::Body)?;
        if tree.k(name) != K::Identifier {
            return None;
        }
        let (only, object) = tree.only_returned_object(body)?;
        Some(ScriptGlobal {
            name: tree.text(name),
            span: tree.span(binding),
            members: self.members(object, Some(node)),
            stable: self.reaches(only, Some(node)),
            source_members: Vec::new(),
            source_origin: false,
            availability: Vec::new(),
        })
    }
}
