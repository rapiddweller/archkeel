// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A local whose one binding is a copy (AD-530, decision 5): `setattr` or `delattr` on it is no
//! write to a module of the scan.
//!
//! `copy.copy` and `copy.deepcopy` of a module raise `TypeError` (CPython 3.12: a module cannot be
//! pickled). A copy is a module object only when a hook gives one: `__copy__`, `__deepcopy__`,
//! `__reduce__`, `__reduce_ex__`, `__new__`, a `copyreg` reductor, a dispatch table of `copy`, or
//! the memo of a `deepcopy` with two arguments. A frame write (`f_locals`, a trace function) can
//! rebind a local. So the proof needs four facts:
//!
//! 1. the first argument is a plain name of the innermost function, and that function (with its
//!    nested scopes) binds the name once: by `name = copier(arg)` in its own scope, with one
//!    positional argument and no keyword;
//! 2. `copier` is `copy` or `deepcopy` of a plain module-scope `from copy import ...`, or the
//!    attribute `copy` or `deepcopy` of a plain module-scope `import copy` (`Bound::of`);
//! 3. no module of the scan names a hook word above, as a name, an attribute, a definition, an
//!    import, a keyword or a string (`names_a_hook`), and no module of the scan is `copy` or
//!    `copyreg` (`uses_scan.rs`);
//! 4. a hook of code outside the scan gives no module object of the scan (the premise). A hook of
//!    the scan that builds its name at run time can give a module object of the scan only by a use
//!    of it as a value: that use is an escape of the module, which withholds its names already.
//!
//! A parameter, an attribute or a subscript of a local, and a local with any other binding keep
//! the gap: a copy keeps the attributes of its source, so `copy(x).attr` can be a module.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    ExceptHandler, Expr, ExprContext, Keyword, Parameter, Pattern, Stmt, StmtFunctionDef, TypeParam,
};
use ruff_text_size::TextSize;

use super::binders::{declared, import_bindings};

/// The names of `copy` whose result is a copy.
const COPIERS: [&str; 2] = ["copy", "deepcopy"];

/// The words of a hook that can make a copy a module object, or rebind a local.
const HOOK_WORDS: [&str; 12] = [
    "__copy__",
    "__deepcopy__",
    "__reduce__",
    "__reduce_ex__",
    "__new__",
    "copyreg",
    "_copy_dispatch",
    "_deepcopy_dispatch",
    "dispatch_table",
    "f_locals",
    "settrace",
    "setprofile",
];

/// The call that binds a copied local: `head(arg)` or `head.attr(arg)`.
#[derive(Clone, Debug, PartialEq, Eq)]
struct Copied {
    /// The plain name that the call starts with.
    head: String,
    /// The attribute of `head` that the call names, if any.
    attr: Option<String>,
}

/// What a walk of a module body finds for the proof (facts 1 and 2).
#[derive(Default)]
pub(super) struct CopyWrites {
    /// The copied locals of each enclosing function, the innermost last.
    copies: Vec<HashMap<String, Copied>>,
    /// The copy call of each `setattr` or `delattr` on a copied local.
    pending: Vec<Copied>,
    /// Each module-scope import of `copy`: the bound name, the statement, the imported name.
    imports: HashMap<String, (TextSize, Option<String>)>,
}

impl CopyWrites {
    /// The walk enters the body of `def`.
    pub(super) fn enter(&mut self, def: &StmtFunctionDef) {
        self.copies.push(copies(def));
    }

    /// The walk leaves the body of the innermost function.
    pub(super) fn leave(&mut self) {
        self.copies.pop();
    }

    /// A module-scope `from copy import ...` or `import copy`.
    pub(super) fn import(&mut self, stmt: &Stmt, start: TextSize) {
        let found: Vec<(String, Option<String>)> = match stmt {
            Stmt::ImportFrom(node) if node.level == 0 && node.module.as_deref() == Some("copy") => {
                (node.names.iter())
                    .map(|alias| {
                        let bound = alias.asname.as_ref().unwrap_or(&alias.name);
                        (bound.to_string(), Some(alias.name.to_string()))
                    })
                    .collect()
            }
            Stmt::Import(node) => (node.names.iter())
                .filter(|alias| alias.name.as_str() == "copy")
                .map(|alias| {
                    (
                        alias.asname.as_ref().unwrap_or(&alias.name).to_string(),
                        None,
                    )
                })
                .collect(),
            _ => Vec::new(),
        };
        for (bound, imported) in found {
            self.imports.insert(bound, (start, imported));
        }
    }

    /// True, and kept for `resolved`, when the first argument of a `setattr` or `delattr` is a
    /// copied local of the innermost function, and the name of its copier is no local of an
    /// enclosing function.
    pub(super) fn write(&mut self, first: &Expr, locals: &[HashSet<String>]) -> bool {
        let Expr::Name(name) = first else {
            return false;
        };
        let Some(call) = self
            .copies
            .last()
            .and_then(|found| found.get(name.id.as_str()))
        else {
            return false;
        };
        if locals.iter().any(|names| names.contains(&call.head)) {
            return false;
        }
        self.pending.push(call.clone());
        true
    }

    /// Whether each kept write has `copy.copy` or `copy.deepcopy` as its copier, by the one plain
    /// import of the module that binds its name (`sole`), and whether there is a kept write.
    pub(super) fn resolved(&self, sole: impl Fn(&str, TextSize) -> bool) -> (bool, bool) {
        let proven = self.pending.iter().all(|call| {
            let Some((start, imported)) = self.imports.get(&call.head) else {
                return false;
            };
            let copier = match (imported, &call.attr) {
                (Some(name), None) | (None, Some(name)) => name.as_str(),
                _ => return false,
            };
            COPIERS.contains(&copier) && sole(&call.head, *start)
        });
        (proven, !self.pending.is_empty())
    }
}

/// The locals of `def` that it binds once, by a copy call in its own scope (fact 1).
fn copies(def: &StmtFunctionDef) -> HashMap<String, Copied> {
    let mut binds = Binds::default();
    for parameter in def.parameters.iter() {
        binds.count(parameter.name().as_str(), 1);
    }
    binds.visit_body(&def.body);
    (binds.own.into_iter())
        .filter(|(name, _)| binds.counts.get(name) == Some(&1))
        .filter_map(|(name, value)| copied(value).map(|call| (name, call)))
        .collect()
}

/// The copy call of a value: one positional argument, no keyword.
fn copied(value: &Expr) -> Option<Copied> {
    let Expr::Call(call) = value else {
        return None;
    };
    let arguments = &call.arguments;
    let [argument] = &*arguments.args else {
        return None;
    };
    if matches!(argument, Expr::Starred(_)) || !arguments.keywords.is_empty() {
        return None;
    }
    match &*call.func {
        Expr::Name(name) => Some(Copied {
            head: name.id.to_string(),
            attr: None,
        }),
        Expr::Attribute(node) if COPIERS.contains(&node.attr.as_str()) => match &*node.value {
            Expr::Name(name) => Some(Copied {
                head: name.id.to_string(),
                attr: Some(node.attr.to_string()),
            }),
            _ => None,
        },
        _ => None,
    }
}

/// Each binding of each name in a function body and its nested scopes, and the value of each
/// `name = value` of the function's own scope.
#[derive(Default)]
struct Binds<'a> {
    counts: HashMap<String, usize>,
    own: HashMap<String, &'a Expr>,
    /// The depth of nested scopes: 0 is the scope of the function.
    depth: usize,
}

impl Binds<'_> {
    fn count(&mut self, name: &str, by: usize) {
        *self.counts.entry(name.to_owned()).or_default() += by;
    }

    fn nested(&mut self, walk: impl FnOnce(&mut Self)) {
        self.depth += 1;
        walk(self);
        self.depth -= 1;
    }
}

impl<'a> Visitor<'a> for Binds<'a> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(node) => {
                self.count(node.name.as_str(), 1);
                self.nested(|walk| visitor::walk_stmt(walk, stmt));
                return;
            }
            Stmt::ClassDef(node) => {
                self.count(node.name.as_str(), 1);
                self.nested(|walk| visitor::walk_stmt(walk, stmt));
                return;
            }
            Stmt::Import(_) | Stmt::ImportFrom(_) => {
                for name in import_bindings(stmt) {
                    self.count(&name, 1);
                }
            }
            // A declared name binds elsewhere: it is never a copied local.
            Stmt::Global(_) | Stmt::Nonlocal(_) => {
                for name in declared(stmt) {
                    self.count(name.as_str(), 2);
                }
            }
            Stmt::Assign(node) if self.depth == 0 => {
                if let [Expr::Name(name)] = node.targets.as_slice() {
                    self.own.insert(name.id.to_string(), &node.value);
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node) if node.ctx != ExprContext::Load => self.count(node.id.as_str(), 1),
            Expr::Lambda(_)
            | Expr::ListComp(_)
            | Expr::SetComp(_)
            | Expr::DictComp(_)
            | Expr::Generator(_) => {
                self.nested(|walk| visitor::walk_expr(walk, expr));
                return;
            }
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        self.count(parameter.name.as_str(), 1);
        visitor::walk_parameter(self, parameter);
    }

    fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
        let ExceptHandler::ExceptHandler(node) = handler;
        if let Some(name) = &node.name {
            self.count(name.as_str(), 1);
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        let name = match pattern {
            Pattern::MatchAs(node) => node.name.as_ref(),
            Pattern::MatchStar(node) => node.name.as_ref(),
            Pattern::MatchMapping(node) => node.rest.as_ref(),
            _ => None,
        };
        if let Some(name) = name {
            self.count(name.as_str(), 1);
        }
        visitor::walk_pattern(self, pattern);
    }

    fn visit_type_param(&mut self, type_param: &'a TypeParam) {
        self.count(type_param.name().as_str(), 1);
        visitor::walk_type_param(self, type_param);
    }
}

/// True when the module names a hook word (fact 3).
pub(super) fn names_a_hook(body: &[Stmt]) -> bool {
    let mut watch = HookWatch(false);
    watch.visit_body(body);
    watch.0
}

struct HookWatch(bool);

impl HookWatch {
    fn word(&mut self, text: &str) {
        self.0 |= HOOK_WORDS.iter().any(|word| text.contains(word));
    }
}

impl<'a> Visitor<'a> for HookWatch {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::FunctionDef(node) => self.word(node.name.as_str()),
            Stmt::ClassDef(node) => self.word(node.name.as_str()),
            Stmt::Import(node) => node.names.iter().for_each(|alias| {
                self.word(alias.name.as_str());
            }),
            Stmt::ImportFrom(node) => {
                node.module
                    .iter()
                    .for_each(|module| self.word(module.as_str()));
                node.names
                    .iter()
                    .for_each(|alias| self.word(alias.name.as_str()));
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node) => self.word(node.id.as_str()),
            Expr::Attribute(node) => self.word(node.attr.as_str()),
            Expr::StringLiteral(node) => self.word(node.value.to_str()),
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }

    fn visit_keyword(&mut self, keyword: &'a Keyword) {
        keyword.arg.iter().for_each(|arg| self.word(arg.as_str()));
        visitor::walk_keyword(self, keyword);
    }
}
