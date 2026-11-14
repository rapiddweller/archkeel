// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The nodes that run a text as code or that bind a global in a script (AD-460). Such code can
//! write any global, also from a module file, so each of them writes an unknown name.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::references::literal;
use crate::script_syntax::Producer;
use crate::script_window::{cooked, Written, CODE_NAMES, TIMERS};

/// The members of a function that call it with other arguments.
const CALLERS: [&str; 3] = ["call", "apply", "bind"];

/// The documents whose `write` adds a script to a page.
const DOCUMENTS: [&str; 3] = ["document", "ownerDocument", "contentDocument"];

/// The members whose HTML text can hold an event handler that runs.
const HTML_MEMBERS: [&str; 3] = ["innerHTML", "outerHTML", "srcdoc"];

/// The calls whose HTML argument can hold an event handler that runs, and the place of it.
const HTML_CALLS: [(&str, usize); 4] = [
    ("insertAdjacentHTML", 1),
    ("createContextualFragment", 0),
    ("setHTMLUnsafe", 0),
    ("parseHTMLUnsafe", 0),
];

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The unknown write that a node that is not a target makes: code from text, a window value
    /// that escapes, or a declaration of a script that binds a global.
    pub(crate) fn node_write(&self, node: Node<'t>) -> Option<Written> {
        if let Some(name) = self.script_declaration(node) {
            return Some(Written::Name(name));
        }
        let unknown = self.runs_code(node)
            || self.injects_code(node)
            || (self.window_leaf(node) && self.escapes(node, true))
            || self.open_form(node);
        unknown.then_some(Written::Unknown)
    }

    /// `eval`, `Function`, a `constructor` member or a timer that can receive a text, used as more
    /// than a read; the text `constructor`; a computed call that can reach `Function`.
    pub(crate) fn runs_code(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let found = match node.kind() {
            "identifier" | "property_identifier" | "shorthand_property_identifier" => {
                self.code_name(node)
            }
            "shorthand_property_identifier_pattern" => self.name_is(node, &["constructor"]),
            "pair_pattern" => tree
                .field(node, F::Key)
                .is_some_and(|key| self.key_is_code(key)),
            "string" | "template_string" => self.constructor_text(node),
            "subscript_expression" => self.computed_code(node),
            _ => false,
        };
        found && !tree.in_type(node) && !tree.declaration_name(node)
    }

    /// The cooked name of the node is one of `names`; an escape that is not plain matches.
    fn name_is(&self, node: Node<'t>, names: &[&str]) -> bool {
        let bytes = self.tree.cx.bytes(node);
        if !bytes.contains(&b'\\') {
            return names.iter().any(|name| name.as_bytes() == bytes);
        }
        cooked(&self.tree.text(node)).is_none_or(|name| names.contains(&name.as_str()))
    }

    fn key_is_code(&self, key: Node<'t>) -> bool {
        match key.kind() {
            "property_identifier" => self.name_is(key, &["constructor"]),
            "computed_property_name" => true,
            _ => crate::script_window::string_text(self, key)
                .is_none_or(|text| text == "constructor"),
        }
    }

    /// A name of code or of a timer: the expression that it names is used as more than a read.
    fn code_name(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        if !self.name_is(node, &CODE_NAMES) && !self.name_is(node, &TIMERS) {
            return false;
        }
        let parent = tree.parent(node);
        let pair_key =
            parent.is_some_and(|p| p.kind() == "pair" && tree.is_field_of_parent(node, F::Key));
        if pair_key {
            return false;
        }
        let member = parent.filter(|p| {
            p.kind() == "member_expression" && tree.is_field_of_parent(node, F::Property)
        });
        let expression = member.unwrap_or(node);
        if member.is_none() && tree.binding_scope(node, &tree.text(node)).is_some() {
            return false;
        }
        let code = self.name_is(node, &CODE_NAMES)
            && (member.is_some() || !self.name_is(node, &["constructor"]));
        if code {
            return self.used(expression);
        }
        self.name_is(node, &TIMERS) && self.timer_runs_text(expression)
    }

    /// The expression is called, passed, stored, or called through `call`, `apply` or `bind`.
    fn used(&self, expression: Node<'t>) -> bool {
        let tree = self.tree;
        let caller = tree.parent(expression).is_some_and(|parent| {
            parent.kind() == "member_expression"
                && tree.is_field_of_parent(expression, F::Object)
                && tree
                    .field(parent, F::Property)
                    .is_some_and(|property| self.name_is(property, &CALLERS))
        });
        caller || self.escapes(expression, false)
    }

    /// A timer that is not called with a function as its first argument.
    fn timer_runs_text(&self, expression: Node<'t>) -> bool {
        let tree = self.tree;
        let call = tree.parent(expression).filter(|parent| {
            parent.kind() == "call_expression" && tree.is_field_of_parent(expression, F::Function)
        });
        let Some(call) = call else {
            return self.used(expression);
        };
        let arguments = tree.field(call, F::Arguments);
        let first = arguments.and_then(|arguments| {
            crate::tree::nodes::named_children(arguments)
                .into_iter()
                .find(|argument| argument.kind() != "comment")
        });
        first.is_some_and(|first| !self.function_value(first))
    }

    /// A function literal, a `bind` result, or a name of the file that is bound once to a function
    /// and never written again.
    fn function_value(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let node = tree.cx.unwrapped(node);
        match node.kind() {
            "function_expression" | "arrow_function" | "generator_function" => true,
            "call_expression" => tree
                .field(node, F::Function)
                .filter(|callee| callee.kind() == "member_expression")
                .and_then(|callee| tree.field(callee, F::Property))
                .is_some_and(|property| tree.text(property) == "bind"),
            "identifier" => self.function_binding(node),
            _ => false,
        }
    }

    fn function_binding(&self, name: Node<'t>) -> bool {
        let tree = self.tree;
        let function = self
            .sole_declaration(name)
            .is_some_and(|declaration| tree.k(declaration) == K::FunctionDeclaration);
        function
            || self.sole_value(name).is_some_and(|value| {
                matches!(value.kind(), "function_expression" | "arrow_function")
            })
    }

    /// The text `constructor` outside a key and a type: a computed key can name it.
    fn constructor_text(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let key = tree.parent(node).is_some_and(|parent| {
            matches!(
                parent.kind(),
                "pair" | "method_definition" | "public_field_definition"
            ) && (tree.is_field_of_parent(node, F::Key) || tree.is_field_of_parent(node, F::Name))
        });
        !key && crate::script_window::string_text(self, node)
            .is_some_and(|text| text == "constructor")
    }

    /// `f[k]` with a key that is not a literal, used as more than a read, on a function, on an
    /// element, on a `constructor` member or on a window: it can reach `Function` or `eval`.
    fn computed_code(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let index = tree.field(node, F::Index);
        if literal(index, tree.cx.source).is_some() || index.is_some_and(|i| i.kind() == "number") {
            return false;
        }
        let Some(object) = tree.field(node, F::Object).map(|o| tree.cx.unwrapped(o)) else {
            return false;
        };
        let reaches = match object.kind() {
            "function_expression"
            | "arrow_function"
            | "generator_function"
            | "class"
            | "subscript_expression" => true,
            "member_expression" => tree
                .field(object, F::Property)
                .is_some_and(|property| self.name_is(property, &["constructor"])),
            "identifier" => self.function_binding(object),
            _ => false,
        };
        (reaches || self.window_value(object)) && self.used(node)
    }

    /// Code that a page runs from a text: `document.write`, an `on…` attribute, a `script`
    /// element, a `javascript:` link and `importScripts`.
    pub(crate) fn injects_code(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        if tree.in_type(node) {
            return false;
        }
        match node.kind() {
            "string" | "template_string" => crate::script_window::string_text(self, node)
                .is_some_and(|text| {
                    text.trim_start()
                        .to_ascii_lowercase()
                        .starts_with("javascript:")
                }),
            "call_expression" => self.injecting_call(node),
            "assignment_expression" | "augmented_assignment_expression" => self.html_write(node),
            _ => false,
        }
    }

    /// A write of HTML text into an element, unless the text is a literal without markup.
    fn html_write(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let target = tree
            .field(node, F::Left)
            .map(|left| tree.cx.unwrapped(left));
        let html = target
            .filter(|t| t.kind() == "member_expression")
            .and_then(|t| {
                tree.field(t, F::Property)
                    .map(|p| HTML_MEMBERS.contains(&tree.text(p).as_str()))
            });
        html == Some(true) && !self.plain_text(tree.field(node, F::Right))
    }

    /// A literal text without `<`: it holds no element and so no handler.
    fn plain_text(&self, node: Option<Node<'t>>) -> bool {
        node.and_then(|node| crate::script_window::string_text(self, node))
            .is_some_and(|text| !text.contains('<'))
    }

    fn injecting_call(&self, call: Node<'t>) -> bool {
        let tree = self.tree;
        let Some(callee) = tree.field(call, F::Function) else {
            return false;
        };
        let arguments: Vec<Node<'t>> = tree
            .field(call, F::Arguments)
            .map(crate::tree::nodes::named_children)
            .unwrap_or_default();
        let text_of = |at: usize| {
            arguments
                .get(at)
                .and_then(|argument| crate::script_window::string_text(self, *argument))
        };
        let (object, name) = match callee.kind() {
            "member_expression" => (
                tree.field(callee, F::Object).map(|o| tree.cx.unwrapped(o)),
                tree.field(callee, F::Property).map(|p| tree.text(p)),
            ),
            "identifier" => (None, Some(tree.text(callee))),
            _ => return false,
        };
        let html = HTML_CALLS
            .iter()
            .find(|(call, _)| name.as_deref() == Some(*call));
        if let Some((_, at)) = html {
            return !self.plain_text(arguments.get(*at).copied());
        }
        match name.as_deref() {
            Some("write" | "writeln") => object.is_some_and(|object| self.document(object)),
            Some("setAttribute") => text_of(0).is_none_or(|text| handler(&text)),
            Some("setAttributeNS") => text_of(1).is_none_or(|text| handler(&text)),
            Some("createElement") => {
                text_of(0).is_none_or(|text| text.eq_ignore_ascii_case("script"))
            }
            Some("createElementNS") => {
                text_of(1).is_none_or(|text| text.eq_ignore_ascii_case("script"))
            }
            Some("importScripts") => true,
            _ => false,
        }
    }

    fn document(&self, object: Node<'t>) -> bool {
        let tree = self.tree;
        let name = match object.kind() {
            "identifier" => tree.text(object),
            "member_expression" => tree
                .field(object, F::Property)
                .map_or_else(String::new, |property| tree.text(property)),
            _ => return false,
        };
        DOCUMENTS.contains(&name.as_str())
    }

    /// A top-level `enum` or `namespace` of a script binds a global of its name at run time.
    pub(crate) fn script_declaration(&self, node: Node<'t>) -> Option<String> {
        let tree = self.tree;
        if self.module_syntax
            || !matches!(
                node.kind(),
                "enum_declaration" | "internal_module" | "module"
            )
        {
            return None;
        }
        let top = tree
            .ancestors(node)
            .all(|above| matches!(above.kind(), "program" | "expression_statement"));
        let constant = tree.has_child_kind(node, K::Const);
        if !top || constant {
            return None;
        }
        let name = tree.field(node, F::Name)?;
        let text = tree.text(name);
        let first = text.split('.').next().unwrap_or_default().trim().to_owned();
        Some(first)
    }
}

/// An attribute name that holds an event handler.
fn handler(name: &str) -> bool {
    name.get(..2)
        .is_some_and(|start| start.eq_ignore_ascii_case("on"))
}
