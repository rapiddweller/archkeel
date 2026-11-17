// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The writes that replace a global in one program outside the scan roots (#1546), and the inline
//! scripts of a page. The reader is syntactic and local to the program: it needs no scope facts of
//! the scan, because the file is no module of the scan.

use std::collections::HashSet;

use tree_sitter::Node;

use crate::source::{Source, Span};
use crate::source_input::is_window_name;

/// A write that replaces a global: its name, or `None` where the reader cannot read the name.
pub(crate) struct Found {
    pub name: Option<String>,
    pub span: Span,
}

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

/// The kinds that pass a declared name up to its declaration.
const PATTERNS: [&str; 9] = [
    "object_pattern",
    "array_pattern",
    "pair_pattern",
    "assignment_pattern",
    "object_assignment_pattern",
    "rest_pattern",
    "required_parameter",
    "optional_parameter",
    "formal_parameters",
];

/// The kinds that declare the name below them.
const DECLARERS: [&str; 17] = [
    "variable_declarator",
    "function_declaration",
    "generator_function_declaration",
    "class_declaration",
    "abstract_class_declaration",
    "function_expression",
    "generator_function",
    "class",
    "arrow_function",
    "catch_clause",
    "import_specifier",
    "namespace_import",
    "import_clause",
    "enum_declaration",
    "internal_module",
    "formal_parameters",
    "for_in_statement",
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
            Node::kind(&node),
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
        if let Some(name) = target.and_then(|target| reader.target(target)) {
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

/// The identifier is a declared name: a name, a pattern or a parameter of a declaration.
fn declares(node: Node) -> bool {
    let mut at = node;
    while let Some(parent) = at.parent() {
        let kind = Node::kind(&parent);
        if DECLARERS.contains(&kind) {
            let field = |name: &str| {
                parent
                    .child_by_field_name(name)
                    .is_some_and(|found| found.id() == at.id())
            };
            return match kind {
                "variable_declarator"
                | "function_declaration"
                | "generator_function_declaration"
                | "class_declaration"
                | "abstract_class_declaration"
                | "function_expression"
                | "generator_function"
                | "class"
                | "enum_declaration"
                | "internal_module" => field("name"),
                "arrow_function" => field("parameter"),
                "catch_clause" => field("parameter"),
                "for_in_statement" => field("left") && parent.child_by_field_name("kind").is_some(),
                _ => true,
            };
        }
        if !PATTERNS.contains(&kind) || !pattern_part(parent, at) {
            return false;
        }
        at = parent;
    }
    false
}

/// `at` is the bound part of the pattern `parent`, not a default value or a key.
fn pattern_part(parent: Node, at: Node) -> bool {
    let is = |name: &str| {
        parent
            .child_by_field_name(name)
            .is_some_and(|found| found.id() == at.id())
    };
    match Node::kind(&parent) {
        "assignment_pattern" | "object_assignment_pattern" => is("left"),
        "required_parameter" | "optional_parameter" => is("pattern"),
        "pair_pattern" => is("value"),
        _ => true,
    }
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
                .any(|c| Node::kind(&c) == "template_substitution");
        quoted
            .then(|| plain(text.get(1..str::len(&text).saturating_sub(1))?))
            .flatten()
    }

    /// The global that a write target replaces: `Some(None)` for a name that cannot be read.
    fn target(&self, target: Node) -> Option<Option<String>> {
        let target = unwrapped(target);
        if Node::kind(&target) == "identifier" {
            let name = Reader::text(self, target);
            return (!self.declared.contains(&name)).then_some(Some(name));
        }
        // The chain from the target down to its root object.
        let mut chain = vec![target];
        while let Some(object) = chain
            .last()
            .filter(|at| {
                matches!(
                    Node::kind(&at),
                    "member_expression" | "subscript_expression"
                )
            })
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
        // A member write of another global (`document.title = t`, `Math.max = f`) changes a member
        // of a platform object, not the global: a member patch is an open limit (AD-788).
        None
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
            .filter(|a| Node::kind(&a) != "comment")
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
            if !self.window(object) {
                return Vec::new();
            }
            let name = arguments.first().and_then(|key| self.literal(*key));
            return vec![Found { name, span: span() }];
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
        if !reflective || !on_window {
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
            .filter(|part| Node::kind(&part) != "comment")
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
                    .filter(|d| Node::kind(&d) == "variable_declarator")
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

/// The length of `<script`.
const SCRIPT_TAG: usize = 7;

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

/// The inline scripts of a page that run as JavaScript, each with a flag for `type="module"` and
/// with every byte outside the script blanked (a line end stays), so the lines stay the lines of
/// the page. A script with `src` holds no code of the page.
pub(crate) fn inline_scripts(data: &[u8]) -> Vec<(bool, Vec<u8>)> {
    let lower = data.to_ascii_lowercase();
    let mut found = Vec::new();
    let mut at = 0;
    while let Some(start) = find(&lower, b"<script", at) {
        let after = start + SCRIPT_TAG;
        let Some(close) = find(&lower, b">", after) else {
            break;
        };
        let attributes = String::from_utf8_lossy(&lower[after..close]).into_owned();
        let end = find(&lower, b"</script", close).unwrap_or(<[u8]>::len(data));
        at = end.max(close + 1);
        let tag = lower
            .get(after)
            .is_some_and(|b| b.is_ascii_whitespace() || *b == b'>');
        let kind = script_type(&attributes);
        if !tag || attributes.contains("src") || kind.is_none() {
            continue;
        }
        let mut program: Vec<u8> = data
            .iter()
            .map(|b| if *b == b'\n' { b'\n' } else { b' ' })
            .collect();
        if let (Some(slot), Some(code)) =
            (program.get_mut(close + 1..end), data.get(close + 1..end))
        {
            slot.copy_from_slice(code);
        }
        Vec::push(&mut found, (kind == Some(true), program));
    }
    found
}

/// The script type of an element: `Some(true)` for a module, `Some(false)` for a classic script,
/// `None` for data or a template.
fn script_type(attributes: &str) -> Option<bool> {
    let Some(at) = attributes.find("type") else {
        return Some(false);
    };
    let value: String = attributes[at + 4..]
        .trim_start()
        .trim_start_matches('=')
        .trim_start()
        .trim_start_matches(['"', '\''])
        .chars()
        .take_while(|c| !matches!(c, '"' | '\'' | ' ' | '>'))
        .collect();
    match String::as_str(&value) {
        "module" => Some(true),
        ""
        | "text/javascript"
        | "application/javascript"
        | "text/ecmascript"
        | "application/ecmascript"
        | "text/jsx"
        | "text/babel" => Some(false),
        _ => None,
    }
}

fn find(haystack: &[u8], needle: &[u8], from: usize) -> Option<usize> {
    haystack
        .get(from..)?
        .windows(<[u8]>::len(needle))
        .position(|window| window == needle)
        .map(|at| at + from)
}
