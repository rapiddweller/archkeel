// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The per-file syntax facts that the single walk of `scan.rs` collects.
//!
//! `parse.py` finds scopes, definitions, import bindings and rebound names with about ten walks,
//! and it climbs the parents of a node for each question. The walk here keeps a stack of the
//! ancestors, with the frame of the scope and a few flags, and answers each question from it.
//! The facts are owned: no tree node outlives the file.

use std::collections::{BTreeSet, HashMap, HashSet};

use tree_sitter::Node;

use crate::ancestors::{
    Entry, Shadow, ERROR_ABOVE, INSIDE_NAMESPACE, IN_FUNCTION_LIKE, IN_REBOUND_FUNCTION,
    IN_UNMODELED_BLOCK,
};
use crate::definitions::{Definition, Defs, Scopes};
use crate::exports::{
    ambient, export_bindings, module_exports, type_exports, ExportBinding, Named, TypeExports,
};
use crate::import_bindings::{of_statement, ImportBinding};
use crate::kinds::{F, K};
use crate::layout::Layout;
use crate::scope::{is_function, scope_kind, Frames, ROOT};
use crate::script_types::Script;
use crate::sites::{Sites, Visit};
use crate::source_input::{SourceKind, Suffix};
use crate::tree::cx::Cx;
use crate::tree::nodes::named_children;

/// The facts of `Syntax` that this phase produces. The reply does not read them yet; the `dump`
/// feature does (AD-323).
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub(crate) struct Syntax {
    pub definitions: Vec<Definition>,
    /// The parents of the definitions: `parent_name` gives the qualified name of a definition.
    pub scopes: Scopes,
    pub import_bindings: Vec<ImportBinding>,
    pub(crate) module_exports: Vec<ExportBinding>,
    pub(crate) type_exports: TypeExports,
    pub rebound_names: Vec<String>,
    pub ambient_globals: Named,
    pub ambient_top_level: Named,
    pub module_file: bool,
    pub declaration_file: bool,
    pub script_mode: bool,
    /// The file has `import` or `export` syntax (`exports.module_syntax`).
    pub module_syntax: bool,
    pub script_bindings: Vec<String>,
    /// The script facts (`script::read`).
    pub script: Script,
    /// The calls, `new` expressions, references and string comparisons (`sites.rs`).
    pub sites: Sites,
}

impl Syntax {
    /// The qualified name of the parent of a definition (`Definition.parent` in Python).
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub(crate) fn parent_name(&self, definition: &Definition) -> Option<String> {
        definition.parent.map(|at| self.scopes.qualified(at))
    }

    /// The facts of a file that could not be parsed: none.
    pub(crate) fn empty() -> Self {
        Self {
            definitions: Vec::new(),
            scopes: Scopes::default(),
            import_bindings: Vec::new(),
            module_exports: Vec::new(),
            type_exports: TypeExports::default(),
            rebound_names: Vec::new(),
            ambient_globals: Vec::new(),
            ambient_top_level: Vec::new(),
            module_file: false,
            declaration_file: false,
            script_mode: false,
            module_syntax: false,
            script_bindings: Vec::new(),
            script: Script::default(),
            sites: Sites::default(),
        }
    }
}

pub(crate) struct Walk<'a, 't> {
    cx: Cx<'a>,
    stack: Vec<Entry<'t>>,
    frames: Frames,
    defs: Defs,
    imports: Vec<ImportBinding>,
    rebound: BTreeSet<String>,
    /// Identifier targets of writes, with the frame that holds the write.
    writes: Vec<(Node<'t>, u32)>,
    sites: Sites,
    /// The named nodes in document order, for the script facts (`script_scope.rs`).
    layout: Layout<'t>,
}

impl<'a, 't> Walk<'a, 't> {
    pub(crate) fn new(cx: Cx<'a>) -> Self {
        let layout = Layout::default();
        Self {
            cx,
            layout,
            stack: Vec::new(),
            frames: Frames::new(),
            defs: Defs::default(),
            imports: Vec::new(),
            rebound: BTreeSet::new(),
            writes: Vec::new(),
            sites: Sites::default(),
        }
    }

    /// Enter a node; `leave` ends it. A token without a name in the grammar is a leaf: it joins
    /// the stack and has no other effect.
    pub(crate) fn enter(&mut self, node: Node<'t>) {
        let cx = self.cx;
        let info = cx.kinds.info(node);
        let kind = info.kind;
        let (seen, parent_frame, parent_var, parent_scope) = match self.stack.last() {
            Some(parent) => (parent.flags, parent.frame, parent.var_frame, parent.scope),
            None => (0, ROOT, ROOT, None),
        };
        let parent_at = self.stack.last().map(|parent| parent.at);
        let at = self.layout.enter(&cx, node, info.named, parent_at);
        if !info.named {
            let shadow = self.stack.last().map_or_else(Shadow::default, |p| p.shadow);
            self.stack.push(Entry {
                node,
                kind,
                flags: seen,
                at,
                frame: parent_frame,
                var_frame: parent_var,
                scope: parent_scope,
                run: Vec::new(),
                shadow,
                callee: false,
                wrapped_call: false,
            });
            return;
        }
        let flags = seen | self.flags_of(node, kind, info.error);
        let (frame, var_frame) = match scope_kind(kind) {
            Some(var) if !self.stack.is_empty() => {
                let frame = self.frames.push(parent_frame);
                (frame, if var { frame } else { parent_var })
            }
            _ => (parent_frame, parent_var),
        };
        self.bind(node, kind, (frame, parent_frame, parent_var));
        match kind {
            K::ImportStatement => self.imports.extend(of_statement(&cx, node)),
            K::AssignmentExpression => self.rebind(node, seen),
            _ => {}
        }
        self.write_targets(node, kind, frame);
        let mut scope = parent_scope;
        if let Some(opened) = self.defs.definition(&cx, node, kind, &self.stack, seen) {
            scope = Some(opened);
        }
        self.defs.variable(&cx, node, kind, &self.stack, seen);
        let extension = self.sites.enter(
            &cx,
            &Visit {
                node,
                kind,
                stack: &self.stack,
                seen,
                scope: parent_scope,
                opened: scope != parent_scope,
            },
        );
        let flags = flags | extension.flags;
        if let Some(parent) = self.stack.last_mut() {
            if matches!(kind, K::Decorator | K::Comment) {
                parent.run.push(node);
            } else {
                parent.run.clear();
            }
        }
        self.stack.push(Entry {
            node,
            kind,
            flags,
            at,
            frame,
            var_frame,
            scope,
            run: Vec::new(),
            shadow: extension.shadow,
            callee: extension.callee,
            wrapped_call: extension.wrapped_call,
        });
    }

    /// The layout of the named nodes that the walk has seen; `finish` does not keep it.
    pub(crate) fn take_layout(&mut self) -> Layout<'t> {
        std::mem::take(&mut self.layout)
    }

    pub(crate) fn leave(&mut self) {
        if let Some(entry) = self.stack.pop() {
            self.layout.leave(entry.at);
        }
    }

    /// The flags that a node adds for its children.
    fn flags_of(&self, node: Node<'t>, kind: K, error: bool) -> u8 {
        let mut flags = if error { ERROR_ABOVE } else { 0 };
        flags |= match kind {
            K::InternalModule => INSIDE_NAMESPACE | IN_FUNCTION_LIKE,
            K::FunctionDeclaration | K::MethodDefinition | K::ArrowFunction => {
                IN_REBOUND_FUNCTION | IN_FUNCTION_LIKE
            }
            K::GeneratorFunctionDeclaration
            | K::FunctionExpression
            | K::GeneratorFunction
            | K::ClassBody => IN_FUNCTION_LIKE,
            K::StatementBlock => {
                let modeled = self
                    .stack
                    .last()
                    .and_then(|parent| self.cx.field(parent.node, F::Body))
                    .is_some_and(|body| body == node);
                if modeled {
                    0
                } else {
                    IN_UNMODELED_BLOCK
                }
            }
            _ => 0,
        };
        flags
    }

    /// `_script_bindings`: the names that this node binds, in the frame that holds them.
    #[expect(
        clippy::excessive_nesting,
        reason = "the function nests blocks deeper than 4: flatten it (AD-327)"
    )]
    fn bind(&mut self, node: Node<'t>, kind: K, frames: (u32, u32, u32)) {
        let (own, parent_frame, parent_var) = frames;
        let cx = self.cx;
        if is_function(kind) {
            for item in cx
                .field(node, F::Parameters)
                .map(named_children)
                .unwrap_or_default()
            {
                self.frames.bind_pattern(&cx, own, item);
            }
            if let Some(parameter) = cx.field(node, F::Parameter) {
                self.frames.bind_pattern(&cx, own, parameter);
            }
        }
        match kind {
            K::CatchClause => {
                if let Some(parameter) = cx.field(node, F::Parameter) {
                    self.frames.bind_pattern(&cx, own, parameter);
                }
            }
            K::ForInStatement => {
                let declaration = cx.field(node, F::Kind);
                if let (Some(declaration), Some(left)) = (declaration, cx.field(node, F::Left)) {
                    let scope = if cx.k(declaration) == K::Var {
                        parent_var
                    } else {
                        own
                    };
                    self.frames.bind_pattern(&cx, scope, left);
                }
            }
            _ => {}
        }
        if matches!(
            kind,
            K::FunctionExpression | K::GeneratorFunction | K::Class
        ) {
            if let Some(name) = cx.field(node, F::Name) {
                self.frames.bind_pattern(&cx, own, name);
            }
        }
        if matches!(
            kind,
            K::VariableDeclarator
                | K::FunctionDeclaration
                | K::GeneratorFunctionDeclaration
                | K::ClassDeclaration
        ) {
            self.bind_declaration(node, kind, parent_frame, parent_var);
        }
    }

    /// `_script_declaration_bindings`.
    fn bind_declaration(&mut self, node: Node<'t>, kind: K, parent_frame: u32, parent_var: u32) {
        let cx = self.cx;
        let Some(name) = cx.field(node, F::Name) else {
            self.frames.blur(ROOT);
            return;
        };
        let function_scoped = kind == K::VariableDeclarator
            && self
                .stack
                .last()
                .is_some_and(|parent| parent.kind == K::VariableDeclaration);
        let scope = if function_scoped {
            parent_var
        } else {
            parent_frame
        };
        self.frames.bind_pattern(&cx, scope, name);
        // Sloppy-script block functions can also bind in their enclosing var scope.
        if kind == K::FunctionDeclaration && parent_var != scope {
            self.frames.bind_pattern(&cx, parent_var, name);
        }
    }

    /// `_rebound_names`: an assignment outside of any function to a plain name.
    fn rebind(&mut self, node: Node<'t>, seen: u8) {
        if seen & IN_REBOUND_FUNCTION != 0 {
            return;
        }
        let cx = self.cx;
        if let Some(left) = cx
            .field(node, F::Left)
            .filter(|left| cx.k(*left) == K::Identifier)
        {
            self.rebound.insert(cx.text(left));
        }
    }

    /// `_script_assignment_targets`: the plain names that a node writes.
    fn write_targets(&mut self, node: Node<'t>, kind: K, frame: u32) {
        let cx = self.cx;
        let target = match kind {
            K::AssignmentExpression | K::AugmentedAssignmentExpression | K::ForInStatement => {
                cx.field(node, F::Left)
            }
            K::UpdateExpression => cx.field(node, F::Argument),
            K::UnaryExpression if cx.has_child(node, K::Delete) => cx.field(node, F::Argument),
            _ => None,
        };
        let Some(target) = target else {
            return;
        };
        for found in crate::scope::assignment_targets(&cx, target) {
            if cx.k(found) == K::Identifier {
                self.writes.push((found, frame));
            }
        }
    }

    /// Close the walk: the facts that need the whole file.
    pub(crate) fn finish(mut self, root: Node, suffix: Option<Suffix>) -> Syntax {
        let cx = self.cx;
        let top = named_children(root);
        let exports = module_exports(&cx, &top);
        // A name that an import binds counts in the frame of the file.
        for item in &self.imports {
            self.frames.bind(ROOT, item.local.clone());
        }
        // Only an import reads the writes of the file.
        let mut memo = HashMap::new();
        let shadowed = self.frames.shadowed_root_names();
        let written: HashSet<String> = if self.imports.is_empty() {
            HashSet::new()
        } else {
            self.writes
                .iter()
                .map(|(target, frame)| (cx.text(*target), *frame))
                .filter(|(name, frame)| {
                    // Only the root frame decides. A name that it does not bind is not written
                    // there. A name that no other frame binds has the root as its nearest binding
                    // at any depth. Only a shadowed name needs the climb.
                    self.frames.count(ROOT, name) > 0
                        && (!shadowed.contains(name.as_str())
                            || self.frames.bound_scope_memo(&mut memo, *frame, name) == Some(ROOT))
                })
                .map(|(name, _)| name)
                .collect()
        };
        let blurred = self.frames.is_ambiguous(ROOT);
        let mut import_bindings = self.imports;
        for item in &mut import_bindings {
            item.source_unique = !blurred
                && self.frames.count(ROOT, &item.local) == 1
                && !written.contains(&item.local);
        }
        let imported: HashSet<String> = import_bindings
            .iter()
            .filter(|item| !item.type_only)
            .map(|item| item.local.clone())
            .collect();
        let declaration_file =
            suffix.is_some_and(|s| s.source_kind() == Some(SourceKind::Declaration));
        let (ambient_globals, ambient_top_level) = ambient(&cx, &top, exports.module_syntax);
        let hinted = suffix.is_some_and(|s| s.format_hint().is_some());
        let script_mode = suffix.is_some_and(|s| {
            s.source_kind() == Some(SourceKind::JavaScript) && s.format_hint().is_none()
        }) && !exports.module_syntax;
        self.sites.finish(&self.frames, cx.source.data, script_mode);
        let (definitions, scopes) = self.defs.finish(&imported, &exports);
        Syntax {
            module_file: exports.module_syntax || (hinted && !declaration_file),
            module_exports: export_bindings(&cx, (root, &top), &self.frames),
            type_exports: type_exports(&cx, root, &top, &self.frames),
            definitions,
            scopes,
            import_bindings,
            rebound_names: self.rebound.into_iter().collect(),
            ambient_globals,
            ambient_top_level,
            declaration_file,
            script_mode,
            module_syntax: exports.module_syntax,
            script_bindings: self.frames.sorted_names(ROOT),
            script: Script::default(),
            sites: self.sites,
        }
    }
}

#[cfg(test)]
#[path = "walk_tests.rs"]
mod tests;
