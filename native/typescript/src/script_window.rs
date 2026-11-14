// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The one check of what a node writes on the global object (AD-460).
//!
//! A write to the property `N` of an object writes the global `N`, unless the object is proven to
//! be a local value. A write with an unknown key, or an escape, of a value that can be a window
//! writes an unknown name. Code that runs text writes an unknown name. Every proof of a script
//! global reads the writes and paths that this check gives.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::script_syntax::Producer;
use crate::source_input::is_window_name;

/// What a node writes on the global object.
pub(crate) enum Written {
    Name(String),
    Unknown,
}

/// The members of an object whose value can be a window.
const WINDOW_MEMBERS: [&str; 5] = [
    "defaultView",
    "contentWindow",
    "parentWindow",
    "view",
    "source",
];

/// The names that run text as code, and the member that reaches `Function` from any function.
pub(crate) const CODE_NAMES: [&str; 3] = ["eval", "Function", "constructor"];

/// The timers that run a text as code when they receive no function.
pub(crate) const TIMERS: [&str; 3] = ["setTimeout", "setInterval", "setImmediate"];

/// What binds `this`, as far as a write through it is concerned.
#[derive(PartialEq, Eq)]
pub(crate) enum Receiver {
    /// The top level of the file.
    Top,
    /// A plain function or an object method: a caller can give it the window.
    Function,
    /// A class method or accessor: an extracted method can receive the window.
    Method,
    /// A constructor, a field initializer or a static block: a new object or the class.
    Bound,
}

/// The text of a name or a string without its escapes; `None` for an escape that is not plain.
pub(crate) fn cooked(text: &str) -> Option<String> {
    if !text.contains('\\') {
        return Some(text.to_owned());
    }
    let mut out = String::new();
    let mut chars = text.chars().peekable();
    while let Some(next) = chars.next() {
        if next != '\\' {
            out.push(next);
            continue;
        }
        match chars.next()? {
            'u' if chars.peek() == Some(&'{') => {
                chars.next();
                let digits: String = chars.by_ref().take_while(|c| *c != '}').collect();
                out.push(char::from_u32(u32::from_str_radix(&digits, 16).ok()?)?);
            }
            'u' => out.push(hex_char(&mut chars, 4)?),
            'x' => out.push(hex_char(&mut chars, 2)?),
            other if other.is_ascii_alphanumeric() => return None,
            other => out.push(other),
        }
    }
    Some(out)
}

fn hex_char(chars: &mut impl Iterator<Item = char>, count: usize) -> Option<char> {
    let digits: String = chars.take(count).collect();
    char::from_u32(u32::from_str_radix(&digits, 16).ok()?)
}

/// The content of a string literal or a template without substitutions, without its escapes.
pub(crate) fn string_text(producer: &Producer, node: Node) -> Option<String> {
    if !matches!(node.kind(), "string" | "template_string")
        || named_kinds(node).any(|kind| kind == "template_substitution")
    {
        return None;
    }
    let text = producer.tree.text(node);
    let inner = text.get(1..text.len().saturating_sub(1))?;
    cooked(inner)
}

fn named_kinds<'t>(node: Node<'t>) -> impl Iterator<Item = &'static str> + 't {
    crate::tree::nodes::named_children(node)
        .into_iter()
        .map(|child| child.kind())
}

impl<'x, 'a, 't> Producer<'x, 'a, 't> {
    /// The one check of a write target: the global name that it writes, if any.
    pub(crate) fn global_write(&self, target: Node<'t>) -> Option<Written> {
        let tree = self.tree;
        let target = tree.cx.unwrapped(target);
        match tree.k(target) {
            K::Identifier | K::ShorthandPropertyIdentifierPattern => {
                let name = tree.text(target);
                let free = tree.binding_scope(target, &name).is_none() && !tree.in_type(target);
                free.then(|| named(cooked(&name)))
            }
            K::MemberExpression => {
                let object = tree.field(target, F::Object)?;
                let property = tree.field(target, F::Property)?;
                let plain = tree.k(property) == K::PropertyIdentifier;
                (plain && !self.proven_local(object)).then(|| named(cooked(&tree.text(property))))
            }
            K::SubscriptExpression => {
                let object = tree.field(target, F::Object)?;
                if self.proven_local(object) {
                    return None;
                }
                let index = tree.field(target, F::Index)?;
                match string_text(self, index) {
                    Some(name) => Some(Written::Name(name)),
                    None if index.kind() == "number" => None,
                    None => (self.window_value(object) || self.open_key_write(object))
                        .then_some(Written::Unknown),
                }
            }
            _ => None,
        }
    }

    /// The global that a deeper write changes: `parent.Lib.run = f` changes the global `Lib`.
    /// The name after the last window value of the object chain is that global. An element of a
    /// window value is a window value too.
    pub(crate) fn changed_global(&self, target: Node<'t>) -> Option<Written> {
        let tree = self.tree;
        let mut chain = vec![tree.cx.unwrapped(target)];
        while let Some(object) = chain.last().and_then(|at| tree.field(*at, F::Object)) {
            chain.push(tree.cx.unwrapped(object));
        }
        let mut window = false;
        let mut changed = None;
        for (at, node) in chain.iter().enumerate().rev() {
            if window && at > 0 {
                changed = Some(*node);
            }
            let element = window && node.kind() == "subscript_expression";
            window = element || self.window_leaf(*node);
        }
        changed.and_then(|node| self.member_name(node))
    }

    /// The name of the member `at`: its property, a literal key, or an unknown name.
    fn member_name(&self, at: Node<'t>) -> Option<Written> {
        let tree = self.tree;
        match at.kind() {
            "member_expression" => {
                let property = tree.field(at, F::Property)?;
                Some(named(cooked(&tree.text(property))))
            }
            "subscript_expression" => {
                let index = tree.field(at, F::Index)?;
                match string_text(self, index) {
                    Some(name) => Some(Written::Name(name)),
                    None if index.kind() == "number" => None,
                    None => Some(Written::Unknown),
                }
            }
            _ => None,
        }
    }

    /// A value that cannot be a window: a local binding of a new value, or `this` that a
    /// constructor, a field or a static block binds, or `this` at the top of a module.
    fn proven_local(&self, object: Node<'t>) -> bool {
        let tree = self.tree;
        let object = tree.cx.unwrapped(object);
        match tree.k(object) {
            K::This => match self.receiver(object) {
                Receiver::Bound => true,
                Receiver::Top => self.module_syntax,
                Receiver::Function | Receiver::Method => false,
            },
            K::Identifier => self.local_new_value(object),
            _ => false,
        }
    }

    /// The one declaration of a name that its scope binds once and that nothing writes again.
    pub(crate) fn sole_declaration(&self, name: Node<'t>) -> Option<Node<'t>> {
        let tree = self.tree;
        let text = tree.text(name);
        let scope = tree.sole_binding_scope(name, &text)?;
        let key = (scope.id(), text);
        if self.index.written.contains(&key) {
            return None;
        }
        match self.index.declared.get(&key).map(Vec::as_slice) {
            Some([declaration]) => Some(*declaration),
            _ => None,
        }
    }

    /// The initializer of the one declarator of a name, without its type wrappers.
    pub(crate) fn sole_value(&self, name: Node<'t>) -> Option<Node<'t>> {
        let tree = self.tree;
        let declaration = self.sole_declaration(name)?;
        (tree.k(declaration) == K::VariableDeclarator)
            .then(|| tree.field(declaration, F::Value))
            .flatten()
            .map(|value| tree.cx.unwrapped(value))
    }

    /// The name is bound once, to a function or to a new value, and nothing writes it again.
    fn local_new_value(&self, name: Node<'t>) -> bool {
        let tree = self.tree;
        let function = self
            .sole_declaration(name)
            .is_some_and(|declaration| tree.k(declaration) == K::FunctionDeclaration);
        function
            || self
                .sole_value(name)
                .is_some_and(|value| new_value(tree.k(value)))
    }

    /// The value can be a window: a window name, a window member, an element of such a value, a
    /// branch of a condition, or `this` that a plain function or the top of a script receives.
    /// The walk uses a list, not a recursion, so a deep expression costs no stack.
    pub(crate) fn window_value(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        let mut pending = vec![node];
        while let Some(next) = pending.pop() {
            let next = tree.cx.unwrapped(next);
            match next.kind() {
                "subscript_expression" => pending.extend(tree.field(next, F::Object)),
                "ternary_expression" | "binary_expression" | "sequence_expression" => {
                    pending.extend(crate::tree::nodes::named_children(next));
                }
                _ if self.window_leaf(next) => return true,
                _ => {}
            }
        }
        false
    }

    /// A name, a `this` or a member that can be a window, read without its operands.
    pub(crate) fn window_leaf(&self, node: Node<'t>) -> bool {
        let tree = self.tree;
        match node.kind() {
            "identifier" => {
                let parameter = tree
                    .parent(node)
                    .is_some_and(|p| p.kind() == "formal_parameters");
                if tree.in_type(node) || tree.declaration_name(node) || parameter {
                    return false;
                }
                let name = tree.text(node);
                if tree.binding_scope(node, &name).is_some() {
                    return self.is_alias(self.wrapper_of(node), &name);
                }
                cooked(&name).is_none_or(|name| is_window_name(&name))
            }
            "this" => match self.receiver(node) {
                Receiver::Function => true,
                Receiver::Top => !self.module_syntax,
                Receiver::Method | Receiver::Bound => false,
            },
            "member_expression" => tree.field(node, F::Property).is_some_and(|property| {
                cooked(&tree.text(property)).is_none_or(|name| {
                    is_window_name(&name) || WINDOW_MEMBERS.contains(&name.as_str())
                })
            }),
            _ => false,
        }
    }

    /// What binds the `this` at a node. A computed name of a class member is read outside it.
    pub(crate) fn receiver(&self, this: Node<'t>) -> Receiver {
        let tree = self.tree;
        let mut skip_member = false;
        for node in tree.ancestors(this) {
            match node.kind() {
                "computed_property_name" => skip_member = true,
                "method_definition" | "public_field_definition" if skip_member => {
                    skip_member = false;
                }
                "function_declaration"
                | "function_expression"
                | "generator_function"
                | "generator_function_declaration" => return Receiver::Function,
                "method_definition" => return self.method_receiver(node),
                "public_field_definition" | "class_static_block" => return Receiver::Bound,
                _ => {}
            }
        }
        Receiver::Top
    }

    fn method_receiver(&self, method: Node<'t>) -> Receiver {
        let tree = self.tree;
        let in_class = tree
            .parent(method)
            .is_some_and(|body| body.kind() == "class_body");
        let name = tree.field(method, F::Name).map(|name| tree.text(name));
        match (in_class, name.as_deref()) {
            (false, _) => Receiver::Function,
            (true, Some("constructor")) => Receiver::Bound,
            (true, _) => Receiver::Method,
        }
    }

    /// The value leaves the place where it is read: it is called, passed, stored or returned.
    /// A member read, a comparison, `typeof`, `!`, `void` and an argument of a script wrapper,
    /// whose parameter is an alias of the window, are no escape. With `elements`, an
    /// element of the value is the value: `f(frames[0])` passes a window.
    pub(crate) fn escapes(&self, node: Node<'t>, elements: bool) -> bool {
        let tree = self.tree;
        let mut at = node;
        loop {
            let Some(parent) = tree.parent(at) else {
                return true;
            };
            match parent.kind() {
                "parenthesized_expression"
                | "as_expression"
                | "satisfies_expression"
                | "non_null_expression"
                | "type_assertion"
                | "ternary_expression"
                | "sequence_expression" => at = parent,
                "binary_expression" if logical(tree, parent) => at = parent,
                "binary_expression" | "unary_expression" => return false,
                "subscript_expression" if elements && tree.is_field_of_parent(at, F::Object) => {
                    at = parent;
                }
                "member_expression" | "subscript_expression" => {
                    return !tree.is_field_of_parent(at, F::Object)
                }
                "arguments" => return !self.wrapper_argument(parent),
                _ => return true,
            }
        }
    }

    /// The arguments of the call of a script wrapper.
    fn wrapper_argument(&self, arguments: Node<'t>) -> bool {
        let call = self.tree.parent(arguments);
        call.is_some_and(|call| self.wrappers.values().any(|w| w.call.id() == call.id()))
    }
}

/// `a || b`, `a && b` and `a ?? b` give one of their operands.
fn logical<'t>(tree: &crate::script_scope::Tree<'_, 't>, node: Node<'t>) -> bool {
    tree.field(node, F::Operator)
        .is_some_and(|operator| matches!(operator.kind(), "||" | "&&" | "??"))
}

/// A value that the expression makes new: it cannot be the window.
fn new_value(kind: K) -> bool {
    matches!(
        kind,
        K::Object
            | K::Array
            | K::Class
            | K::ClassExpression
            | K::FunctionExpression
            | K::GeneratorFunction
            | K::ArrowFunction
            | K::String
            | K::Number
            | K::TemplateString
            | K::True
            | K::False
            | K::Null
    )
}

pub(crate) fn named(name: Option<String>) -> Written {
    name.map_or(Written::Unknown, Written::Name)
}
