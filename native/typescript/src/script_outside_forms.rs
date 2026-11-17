// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The writes that replace a global in one program outside the scan roots (#1546). The reader is syntactic and local to the program: it needs no scope facts of
//! the scan, because the file is no module of the scan.

use std::collections::HashSet;

use tree_sitter::Node;

use crate::script_outside_names::declares;
use crate::source::{Source, Span};
use crate::source_input::is_window_name;

/// A write that replaces a global: its name, or `None` where the reader cannot read the name.
pub(crate) struct Found {
    pub name: Option<String>,
    pub span: Span,
}

/// The kinds of a literal value: it is no function.
const LITERALS: [&str; 7] = [
    "string",
    "number",
    "true",
    "false",
    "null",
    "undefined",
    "template_string",
];

/// The members of `Object` and `Reflect` that write members of their first argument (AD-766).
const REFLECTIVE: [(&str, &str); 7] = [
    ("Object", "assign"),
    ("Object", "defineProperty"),
    ("Object", "defineProperties"),
    ("Object", "setPrototypeOf"),
    ("Reflect", "set"),
    ("Reflect", "defineProperty"),
    ("Reflect", "setPrototypeOf"),
];

struct Reader<'s> {
    source: Source<'s>,
    bytes: &'s [u8],
    declared: HashSet<String>,
}

/// Each write of the program that replaces a global. `module` says that the element of a page
/// made the program a module; a code file is a module when it has a top-level import or export.
pub(crate) fn writes_of(root: Node, bytes: &[u8], module: bool) -> Vec<Found> {
    let mut reader = Reader {
        source: Source::new(bytes),
        bytes,
        declared: HashSet::new(),
    };
    let nodes = all_nodes(root);
    for node in &nodes {
        if matches!(
            Node::kind(node),
            "identifier" | "shorthand_property_identifier_pattern"
        ) && declares(*node)
        {
            reader.declared.insert(Reader::text(&reader, *node));
        }
    }
    let mut found = Vec::new();
    let module = module
        || named_children(root)
            .iter()
            .any(|top| top_level_module(*top));
    if !module {
        found.extend(reader.script_bindings(root));
    }
    for node in nodes {
        let target = match Node::kind(&node) {
            "assignment_expression" | "augmented_assignment_expression" => {
                node.child_by_field_name("left")
            }
            "update_expression" => node.child_by_field_name("argument"),
            "call_expression" => {
                found.extend(reader.reflective(node));
                None
            }
            _ => None,
        };
        let value = node.child_by_field_name("right");
        if let Some(name) = target.and_then(|target| reader.target(target, value)) {
            Vec::push(
                &mut found,
                Found {
                    name,
                    span: reader.source.span(node, None),
                },
            );
        }
    }
    found
}

/// A top-level `import` or `export` makes a program a module.
fn top_level_module(node: Node) -> bool {
    matches!(Node::kind(&node), "import_statement" | "export_statement")
}

/// The nodes of the tree in document order, without a recursion.
fn all_nodes(root: Node) -> Vec<Node> {
    let mut found = Vec::new();
    let mut pending = vec![root];
    while let Some(node) = pending.pop() {
        Vec::push(&mut found, node);
        let mut children = named_children(node);
        children.reverse();
        pending.extend(children);
    }
    found
}

impl Reader<'_> {
    fn text(&self, node: Node) -> String {
        node.utf8_text(self.bytes).unwrap_or_default().to_owned()
    }

    /// A free name of the global object (`window`, `globalThis`, …).
    fn window(&self, node: Node) -> bool {
        let node = unwrapped(node);
        let name = Reader::text(self, node);
        Node::kind(&node) == "identifier" && is_window_name(&name) && !self.declared.contains(&name)
    }

    /// The name of a member: its property or a literal key; `None` for a run-time key.
    fn member(&self, node: Node) -> Option<String> {
        match Node::kind(&node) {
            "member_expression" => node
                .child_by_field_name("property")
                .and_then(|p| plain(&Reader::text(self, p))),
            _ => node
                .child_by_field_name("index")
                .and_then(|i| self.literal(i)),
        }
    }

    fn literal(&self, node: Node) -> Option<String> {
        let text = Reader::text(self, node);
        let quoted = matches!(Node::kind(&node), "string" | "template_string")
            && !named_children(node)
                .iter()
                .any(|c| Node::kind(c) == "template_substitution");
        quoted
            .then(|| plain(text.get(1..str::len(&text).saturating_sub(1))?))
            .flatten()
    }

    /// The global that a write target replaces: `Some(None)` for a name that cannot be read.
    fn target(&self, target: Node, value: Option<Node>) -> Option<Option<String>> {
        let target = unwrapped(target);
        if Node::kind(&target) == "identifier" {
            let name = Reader::text(self, target);
            return (!self.declared.contains(&name)).then_some(Some(name));
        }
        // The chain from the target down to its root object.
        let mut chain = vec![target];
        while let Some(object) = chain
            .last()
            .filter(|at| matches!(Node::kind(at), "member_expression" | "subscript_expression"))
            .and_then(|at| at.child_by_field_name("object"))
        {
            Vec::push(&mut chain, unwrapped(object));
        }
        let root = *chain.last()?;
        let accessors = &chain[..Vec::len(&chain) - 1];
        if self.window(root) {
            // `window.self.open = f` writes `open`: skip the window names after the root.
            let first = accessors
                .iter()
                .rev()
                .find(|at| self.member(**at).is_none_or(|name| !is_window_name(&name)))?;
            return Some(self.member(*first));
        }
        // A member patch of another global (`Math.max = f`, #1674): a call of the member runs the
        // value. A literal value can be no function.
        let name = Reader::text(self, root);
        let global = Node::kind(&root) == "identifier" && !self.declared.contains(&name);
        let literal = value.is_some_and(|value| LITERALS.contains(&Node::kind(&unwrapped(value))));
        (global && !literal).then_some(Some(name))
    }

    /// `Some(Some(name))` for an undeclared name, `None` for any other node.
    fn free(&self, node: Node) -> Option<Option<String>> {
        let name = Reader::text(self, node);
        let global = Node::kind(&node) == "identifier" && !self.declared.contains(&name);
        global.then_some(Some(name))
    }

    /// A reflective write on a window name: `Object.defineProperty(window, 'x', …)` and the other
    /// members of `REFLECTIVE`, and `window.__defineGetter__('x', …)`.
    fn reflective(&self, call: Node) -> Vec<Found> {
        let span = || self.source.span(call, None);
        let Some(callee) = call.child_by_field_name("function").map(unwrapped) else {
            return Vec::new();
        };
        let arguments: Vec<Node> = call
            .child_by_field_name("arguments")
            .map(named_children)
            .unwrap_or_default()
            .into_iter()
            .filter(|a| Node::kind(a) != "comment")
            .collect();
        let Some(method) = self
            .member(callee)
            .filter(|_| Node::kind(&callee) != "identifier")
        else {
            return Vec::new();
        };
        let Some(object) = callee.child_by_field_name("object").map(unwrapped) else {
            return Vec::new();
        };
        if matches!(
            String::as_str(&method),
            "__defineGetter__" | "__defineSetter__"
        ) {
            // `window.__defineGetter__('x', g)` writes `x`; `console.__defineGetter__('log', g)`
            // patches `console` (#1674).
            let name = if self.window(object) {
                Some(arguments.first().and_then(|key| self.literal(*key)))
            } else {
                self.free(object)
            };
            return name
                .map(|name| Found { name, span: span() })
                .into_iter()
                .collect();
        }
        let owner = if self.window(object) {
            None
        } else if Node::kind(&object) == "identifier"
            && !self.declared.contains(&Reader::text(self, object))
        {
            Some(Reader::text(self, object))
        } else {
            object
                .child_by_field_name("object")
                .filter(|root| self.window(*root))
                .and_then(|_| self.member(object))
        };
        let reflective = owner
            .as_deref()
            .is_some_and(|owner| REFLECTIVE.contains(&(owner, String::as_str(&method))));
        let on_window = arguments.first().is_some_and(|first| self.window(*first));
        if reflective && !on_window {
            // A reflective patch of another global: `Object.assign(Math, { max: f })` (#1674).
            let patched = arguments
                .first()
                .map(|first| unwrapped(*first))
                .filter(|first| {
                    Node::kind(first) == "identifier"
                        && !self.declared.contains(&Reader::text(self, *first))
                });
            return patched
                .map(|first| Found {
                    name: Some(Reader::text(self, first)),
                    span: span(),
                })
                .into_iter()
                .collect();
        }
        if !reflective {
            return Vec::new();
        }
        let names: Vec<Option<String>> = match String::as_str(&method) {
            "defineProperty" | "set" => vec![arguments.get(1).and_then(|k| self.literal(*k))],
            "assign" | "defineProperties" => arguments
                .iter()
                .skip(1)
                .flat_map(|object| self.keys(*object))
                .collect(),
            _ => vec![None],
        };
        names
            .into_iter()
            .map(|name| Found { name, span: span() })
            .collect()
    }

    /// The keys of an object literal; one `None` for a computed key, a spread or another value.
    fn keys(&self, object: Node) -> Vec<Option<String>> {
        let object = unwrapped(object);
        if Node::kind(&object) != "object" {
            return vec![None];
        }
        named_children(object)
            .into_iter()
            .filter(|part| Node::kind(part) != "comment")
            .map(|part| match Node::kind(&part) {
                "shorthand_property_identifier" => Some(Reader::text(self, part)),
                "pair" | "method_definition" => {
                    let key = part
                        .child_by_field_name("key")
                        .or_else(|| part.child_by_field_name("name"))?;
                    match Node::kind(&key) {
                        "property_identifier" => plain(&Reader::text(self, key)),
                        _ => self.literal(key),
                    }
                }
                _ => None,
            })
            .collect()
    }

    /// The top-level bindings of a classic script: each one is a global of the page.
    fn script_bindings(&self, root: Node) -> Vec<Found> {
        let mut found = Vec::new();
        for top in named_children(root) {
            let names: Vec<Node> = match Node::kind(&top) {
                "lexical_declaration" | "variable_declaration" => named_children(top)
                    .into_iter()
                    .filter(|d| Node::kind(d) == "variable_declarator")
                    .filter_map(|d| d.child_by_field_name("name"))
                    .collect(),
                "function_declaration"
                | "generator_function_declaration"
                | "class_declaration"
                | "enum_declaration"
                | "internal_module" => top.child_by_field_name("name").into_iter().collect(),
                _ => Vec::new(),
            };
            for name in names {
                let text = (Node::kind(&name) == "identifier").then(|| Reader::text(self, name));
                Vec::push(
                    &mut found,
                    Found {
                        name: text,
                        span: self.source.span(top, None),
                    },
                );
            }
        }
        found
    }
}

/// The named children of a node.
fn named_children(node: Node) -> Vec<Node> {
    let mut cursor = node.walk();
    node.named_children(&mut cursor).collect()
}

/// A name without escapes; a name with an escape is one that the reader does not read.
fn plain(text: &str) -> Option<String> {
    (!text.contains('\\')).then(|| text.to_owned())
}

/// The node without parentheses and type wrappers.
fn unwrapped(node: Node) -> Node {
    let mut at = node;
    while matches!(
        Node::kind(&at),
        "parenthesized_expression"
            | "as_expression"
            | "non_null_expression"
            | "satisfies_expression"
            | "type_assertion"
    ) {
        match named_children(at).first() {
            Some(inner) => at = *inner,
            None => break,
        }
    }
    at
}
