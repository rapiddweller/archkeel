// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The per-file syntax facts that the single walk of `scan.rs` collects.
//!
//! `parse.py` finds scopes, definitions, import bindings and rebound names with about ten walks,
//! and it climbs the parents of a node for each question. The walk here keeps a stack of the
//! ancestors, with the frame of the scope and a few flags, and answers each question from it.
//! The facts are owned: no tree node outlives the file.

use std::collections::{BTreeSet, HashSet};

use tree_sitter::Node;

use crate::definitions::{Definition, Defs, Scopes};
use crate::exports::{ambient, export_bindings, module_exports, Named};
use crate::import_bindings::{of_statement, ImportBinding};
use crate::kinds::{F, K};
use crate::members::{named_children, Cx};
use crate::scope::{is_function, scope_kind, Frames, ROOT};
use crate::source_input::{SourceKind, Suffix};
use crate::syntax::Span;

/// An ancestor is a node the parser had to repair.
pub const ERROR_ABOVE: u8 = 1;
/// An ancestor is an `internal_module` (`namespace` or `module`).
pub const INSIDE_NAMESPACE: u8 = 2;
/// An ancestor is a statement block that is not the `body` of its parent.
pub const IN_UNMODELED_BLOCK: u8 = 4;
/// An ancestor is a function declaration, a method or an arrow function.
pub const IN_REBOUND_FUNCTION: u8 = 8;
/// An ancestor is a function, a class body or a namespace.
pub const IN_FUNCTION_LIKE: u8 = 16;

/// One node on the path from the root to the node that the walk visits.
pub struct Entry<'t> {
    pub node: Node<'t>,
    pub kind: K,
    /// The flags that the children of this node see.
    pub flags: u8,
    /// The frame of the nearest scope, this node included.
    pub frame: u32,
    /// The frame of the nearest `var` scope, this node included.
    pub var_frame: u32,
    /// The nearest definition that holds this node, this node included.
    pub scope: Option<u32>,
    /// The decorators and comments among the named children seen so far that directly precede
    /// the next child.
    pub run: Vec<Node<'t>>,
}

/// The facts of `Syntax` that this phase produces. The reply does not read them yet; the `dump`
/// feature does (AD-322).
#[cfg_attr(not(feature = "dump"), allow(dead_code))]
pub struct Syntax {
    pub definitions: Vec<Definition>,
    /// The parents of the definitions: `parent_name` gives the qualified name of a definition.
    pub scopes: Scopes,
    pub import_bindings: Vec<ImportBinding>,
    pub module_exports: Vec<(String, Span, Span)>,
    pub rebound_names: Vec<String>,
    pub ambient_globals: Named,
    pub ambient_top_level: Named,
    pub module_file: bool,
    pub declaration_file: bool,
    pub script_mode: bool,
    pub script_bindings: Vec<String>,
}

impl Syntax {
    /// The qualified name of the parent of a definition (`Definition.parent` in Python).
    #[cfg_attr(not(feature = "dump"), allow(dead_code))]
    pub fn parent_name(&self, definition: &Definition) -> Option<String> {
        definition.parent.map(|at| self.scopes.qualified(at))
    }

    /// The facts of a file that could not be parsed: none.
    pub fn empty() -> Self {
        Self {
            definitions: Vec::new(),
            scopes: Scopes::default(),
            import_bindings: Vec::new(),
            module_exports: Vec::new(),
            rebound_names: Vec::new(),
            ambient_globals: Vec::new(),
            ambient_top_level: Vec::new(),
            module_file: false,
            declaration_file: false,
            script_mode: false,
            script_bindings: Vec::new(),
        }
    }
}

pub struct Walk<'a, 't> {
    cx: Cx<'a>,
    stack: Vec<Entry<'t>>,
    frames: Frames,
    defs: Defs,
    imports: Vec<ImportBinding>,
    rebound: BTreeSet<String>,
    /// Identifier targets of writes, with the frame that holds the write.
    writes: Vec<(Node<'t>, u32)>,
}

impl<'a, 't> Walk<'a, 't> {
    pub fn new(cx: Cx<'a>) -> Self {
        Self {
            cx,
            stack: Vec::new(),
            frames: Frames::new(),
            defs: Defs::default(),
            imports: Vec::new(),
            rebound: BTreeSet::new(),
            writes: Vec::new(),
        }
    }

    /// Enter a node; `leave` ends it. A token without a name in the grammar is a leaf: it joins
    /// the stack and has no other effect.
    pub fn enter(&mut self, node: Node<'t>) {
        let cx = self.cx;
        let info = cx.kinds.info(node);
        let kind = info.kind;
        let (seen, parent_frame, parent_var, parent_scope) = match self.stack.last() {
            Some(parent) => (parent.flags, parent.frame, parent.var_frame, parent.scope),
            None => (0, ROOT, ROOT, None),
        };
        if !info.named {
            self.stack.push(Entry {
                node,
                kind,
                flags: seen,
                frame: parent_frame,
                var_frame: parent_var,
                scope: parent_scope,
                run: Vec::new(),
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
            frame,
            var_frame,
            scope,
            run: Vec::new(),
        });
    }

    pub fn leave(&mut self) {
        self.stack.pop();
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
    pub fn finish(mut self, root: Node, suffix: Option<Suffix>) -> Syntax {
        let cx = self.cx;
        let top = named_children(root);
        let exports = module_exports(&cx, &top);
        // A name that an import binds counts in the frame of the file.
        for item in &self.imports {
            self.frames.bind(ROOT, item.local.clone());
        }
        let written: HashSet<String> = self
            .writes
            .iter()
            .map(|(target, frame)| (cx.text(*target), *frame))
            .filter(|(name, frame)| self.frames.bound_scope(*frame, name) == Some(ROOT))
            .map(|(name, _)| name)
            .collect();
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
        let (definitions, scopes) = self.defs.finish(&imported, &exports);
        Syntax {
            module_file: exports.module_syntax || (hinted && !declaration_file),
            module_exports: export_bindings(&cx, (root, &top), &self.frames),
            definitions,
            scopes,
            import_bindings,
            rebound_names: self.rebound.into_iter().collect(),
            ambient_globals,
            ambient_top_level,
            declaration_file,
            script_mode,
            script_bindings: self.frames.sorted_names(ROOT),
        }
    }
}

#[cfg(test)]
#[path = "walk_tests.rs"]
mod tests;
