// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The script facts of one file (AD-340, PR 4.3a-4): what `parse._script_globals`,
//! `_script_declarations`, `_script_aliases`, `_script_factories`, `_script_destructures` and
//! `_script_namespaces` put into `Syntax`. They read the tree of the file after the walk, because
//! they need the bindings of every scope.

use std::rc::Rc;

use tree_sitter::Node;

use crate::layout::Layout;
use crate::script_scope::Tree;
use crate::script_syntax::Producer;
use crate::script_types::Script;
use crate::source::Span;
use crate::tree::cx::Cx;
use crate::umd::Templates;
use crate::walk::Syntax;

/// The script facts of a file whose other facts are in `syntax`, and the places where a scope that
/// binds names cannot be known (a concern of a global script).
pub(crate) fn read<'t>(
    cx: Cx,
    root: Node<'t>,
    layout: Layout<'t>,
    syntax: &Syntax,
    templates: &Templates,
) -> (Script, Vec<Span>) {
    let mut tree = Tree::from_layout(cx, root, layout);
    let nodes = Rc::clone(&tree.nodes);
    tree.bind(&nodes, &syntax.import_bindings);
    let module_syntax = syntax.module_syntax;
    let producer = Producer::new(
        &tree,
        &syntax.definitions,
        &syntax.scopes,
        module_syntax,
        templates,
    );
    let (mut globals, mut writes) = producer.globals();
    let declared = producer.declarations();
    writes.extend(declared.checked.iter().cloned());
    let writes = crate::script_syntax::unique(writes);
    for item in &mut globals {
        if let Some(members) = declared.members.get(&item.span) {
            item.source_members.clone_from(members);
        }
    }
    let mut script = Script {
        writes,
        source_writes: declared.writes,
        write_paths: declared.paths,
        top_level_write_paths: declared.top_level_paths,
        ..Script::default()
    };
    let mut ambiguous = Vec::new();
    if syntax.script_mode {
        let listed = nodes
            .iter()
            .filter(|node| tree.ambiguous.contains(&node.id()));
        ambiguous = listed.map(|node| tree.span(*node)).collect();
        script.globals = globals;
        script.aliases = producer.aliases();
        script.factories = producer.factories();
        script.destructures = producer.destructures();
        script.namespaces = producer.namespaces();
    }
    (script, ambiguous)
}

#[cfg(test)]
#[path = "script_tests.rs"]
mod tests;
