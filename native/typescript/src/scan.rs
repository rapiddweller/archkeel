// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The nodes that import extraction needs, found in one walk over the tree.
//!
//! `parse.py` finds them with seven queries, and each query walks the whole tree. One walk with a
//! match on the node kind finds the same nodes. `scan_tests.rs` keeps the seven queries as the
//! reference and compares both on real files. The same walk feeds `Walk`, which keeps the stack of
//! the ancestors and collects the syntax facts of the file (AD-323).

use tree_sitter::{Language, Node, TreeCursor};

use crate::plant;
use crate::source::Source;
use crate::walk::Walk;

/// The ids of the node kinds that the walk matches, resolved once for a grammar.
#[derive(Clone, Copy)]
pub struct Kinds {
    import_statement: u16,
    export_statement: u16,
    call_expression: u16,
    import: u16,
    identifier: u16,
    type_identifier: u16,
    shorthand: u16,
    shorthand_pattern: u16,
    property_identifier: u16,
    string_fragment: u16,
    string: u16,
    module: u16,
    comment: u16,
    member_expression: u16,
    subscript_expression: u16,
    pair_pattern: u16,
}

impl Kinds {
    pub fn new(language: &Language) -> Self {
        let named = |name: &str| language.id_for_node_kind(name, true);
        Self {
            import_statement: named("import_statement"),
            export_statement: named("export_statement"),
            call_expression: named("call_expression"),
            import: named("import"),
            identifier: named("identifier"),
            type_identifier: named("type_identifier"),
            shorthand: named("shorthand_property_identifier"),
            shorthand_pattern: named("shorthand_property_identifier_pattern"),
            property_identifier: named("property_identifier"),
            string_fragment: named("string_fragment"),
            string: named("string"),
            module: named("module"),
            comment: named("comment"),
            member_expression: named("member_expression"),
            subscript_expression: named("subscript_expression"),
            pair_pattern: named("pair_pattern"),
        }
    }
}

/// The nodes of each kind that import extraction reads, in document order.
#[derive(Default)]
pub struct Scan<'t> {
    pub imports: Vec<Node<'t>>,
    /// `export ... from`: an export statement with a source.
    pub exports: Vec<Node<'t>>,
    /// `import(...)`.
    pub dynamic: Vec<Node<'t>>,
    /// `require(...)`.
    pub requires: Vec<Node<'t>>,
    pub comments: Vec<Node<'t>>,
    /// The string names of `declare module "x"`.
    pub augmentations: Vec<Node<'t>>,
    /// Nodes that the parser had to repair or invent.
    pub errors: Vec<Node<'t>>,
    /// Every name `require`.
    pub require_names: Vec<Node<'t>>,
    /// `x.require`.
    pub require_members: Vec<Node<'t>>,
    /// `x["require"]` and `module[x]`.
    pub subscripts: Vec<Node<'t>>,
    /// `{ key: value }` in a pattern.
    pub pairs: Vec<Node<'t>>,
    /// Whether the name `module` occurs.
    pub module_name: bool,
    /// Every name `createRequire`.
    pub create_require: Vec<Node<'t>>,
}

fn is_text(source: &Source, node: Node, text: &[u8]) -> bool {
    source.data.get(node.start_byte()..node.end_byte()) == Some(text)
}

/// `^.require.$`: a string literal of the text `require`, with one quote on each side.
fn is_require_literal(source: &Source, node: Node) -> bool {
    let Some(bytes) = source.data.get(node.start_byte()..node.end_byte()) else {
        return false;
    };
    let text = String::from_utf8_lossy(bytes);
    let chars: Vec<char> = text.chars().collect();
    chars.len() == 9
        && chars[1..8].iter().collect::<String>() == "require"
        && chars[0] != '\n'
        && chars[8] != '\n'
}

fn field_kind<'t>(node: Node<'t>, field: &str) -> Option<(u16, Node<'t>)> {
    let child = node.child_by_field_name(field)?;
    Some((child.kind_id(), child))
}

#[expect(
    clippy::cognitive_complexity,
    reason = "the function is over 15 in cognitive complexity: simplify it (AD-327)"
)]
fn visit<'t>(kinds: &Kinds, source: &Source, node: Node<'t>, found: &mut Scan<'t>) {
    if node.is_error() || node.is_missing() {
        found.errors.push(node);
    }
    let kind = node.kind_id();
    if kind == kinds.identifier
        || kind == kinds.type_identifier
        || kind == kinds.shorthand
        || kind == kinds.shorthand_pattern
        || kind == kinds.property_identifier
        || kind == kinds.string_fragment
    {
        name(kinds, source, node, kind, found);
    } else if kind == kinds.import_statement {
        if !plant::lose("import") {
            found.imports.push(node);
        }
    } else if kind == kinds.export_statement {
        let sourced = node
            .child_by_field_name("source")
            .is_some_and(|source| source.is_named());
        if sourced && !plant::lose("export") {
            found.exports.push(node);
        }
    } else if kind == kinds.call_expression {
        match field_kind(node, "function") {
            Some((id, _)) if id == kinds.import && !plant::lose("dynamic") => {
                found.dynamic.push(node);
            }
            Some((id, callee))
                if id == kinds.identifier
                    && is_text(source, callee, b"require")
                    && !plant::lose("require") =>
            {
                found.requires.push(node);
            }
            _ => {}
        }
    } else if kind == kinds.comment {
        found.comments.push(node);
    } else if kind == kinds.module {
        if let Some((id, name)) = field_kind(node, "name") {
            if id == kinds.string {
                found.augmentations.push(name);
            }
        }
    } else if kind == kinds.member_expression {
        if let Some((id, property)) = field_kind(node, "property") {
            if id == kinds.property_identifier && is_text(source, property, b"require") {
                found.require_members.push(node);
            }
        }
    } else if kind == kinds.subscript_expression {
        subscript(kinds, source, node, found);
    } else if kind == kinds.pair_pattern && node.child_by_field_name("key").is_some() {
        found.pairs.push(node);
    }
}

/// The names that matter: `require`, `module` and `createRequire`, in the kinds that each query
/// of `parse.py` lists.
fn name<'t>(kinds: &Kinds, source: &Source, node: Node<'t>, kind: u16, found: &mut Scan<'t>) {
    let Some(text) = source.data.get(node.start_byte()..node.end_byte()) else {
        return;
    };
    let type_name = kind == kinds.type_identifier;
    let member_or_fragment = kind == kinds.property_identifier || kind == kinds.string_fragment;
    if text == b"require" && !member_or_fragment {
        found.require_names.push(node);
    } else if text == b"module" && kind == kinds.identifier {
        found.module_name = true;
    } else if text == b"createRequire" && !type_name {
        found.create_require.push(node);
    }
}

fn subscript<'t>(kinds: &Kinds, source: &Source, node: Node<'t>, found: &mut Scan<'t>) {
    if let Some((id, index)) = field_kind(node, "index") {
        if id == kinds.string && is_require_literal(source, index) {
            found.subscripts.push(node);
        }
    }
    if let Some((id, object)) = field_kind(node, "object") {
        if id == kinds.identifier && is_text(source, object, b"module") {
            found.subscripts.push(node);
        }
    }
}

/// Walk the tree once, in document order, and sort each node into its list. `walk` sees each node
/// on the way down and on the way up, so it keeps the ancestors of the node that it visits.
pub fn scan<'t>(
    kinds: &Kinds,
    source: &Source,
    root: Node<'t>,
    walk: &mut Walk<'_, 't>,
) -> Scan<'t> {
    let mut found = Scan::default();
    let mut cursor: TreeCursor<'t> = root.walk();
    loop {
        let node = cursor.node();
        visit(kinds, source, node, &mut found);
        walk.enter(node);
        if cursor.goto_first_child() {
            continue;
        }
        walk.leave();
        while !cursor.goto_next_sibling() {
            if !cursor.goto_parent() {
                return found;
            }
            walk.leave();
        }
    }
}

#[cfg(test)]
#[path = "scan_tests.rs"]
mod tests;
