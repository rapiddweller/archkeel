// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Methods whose class may be a declaration rather than an implementation.

use std::collections::{HashMap, HashSet};

use archkeel_facts::ids::ModuleName;
use archkeel_facts::type_shape::Binding;
use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt, StmtClassDef, StmtFunctionDef};

use super::shape_names::Names;
use crate::module::Module;
use crate::survey::binders::Binders;

pub(in crate::survey) fn withheld(
    module: &Module,
    binders: &Binders,
    imports: &[&Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
) -> HashSet<String> {
    let names = Names::of((&module.name, &module.tree), binders, imports, sets);
    let mut walk = Declarations {
        names: &names,
        binders,
        owner: module.name.clone(),
        class: None,
        in_function: false,
        found: HashSet::new(),
    };
    walk.visit_body(&module.tree.body);
    walk.found
}

pub(in crate::survey) fn by_module(
    imports: &[Record<ImportFact>],
) -> HashMap<&str, Vec<&Record<ImportFact>>> {
    let mut found: HashMap<&str, Vec<&Record<ImportFact>>> = HashMap::new();
    for record in imports {
        found
            .entry(ModuleName::as_str(
                &ImportFact::data(&record.data).source_module,
            ))
            .or_default()
            .push(record);
    }
    found
}

struct Declarations<'a> {
    names: &'a Names<'a>,
    binders: &'a Binders,
    owner: String,
    class: Option<bool>,
    in_function: bool,
    found: HashSet<String>,
}

impl Declarations<'_> {
    fn decorator_is_unread(&self, node: &StmtFunctionDef) -> bool {
        if matches!(&node.decorator_list[..], []) {
            return false;
        }
        let [decorator] = node.decorator_list.as_slice() else {
            return true;
        };
        let Expr::Name(name) = &decorator.expression else {
            return true;
        };
        self.class.is_none()
            || !matches!(&*name.id, "staticmethod" | "classmethod" | "property")
            || !self.binders.builtin_visible(&name.id)
    }

    fn may_declare(&self, node: &StmtClassDef) -> bool {
        if !matches!(&node.decorator_list[..], []) {
            return true;
        }
        let Some(arguments) = &node.arguments else {
            return false;
        };
        if !matches!(&arguments.keywords[..], [])
            || (!matches!(&arguments.args[..], []) && (self.class.is_some() || self.in_function))
        {
            return true;
        }
        arguments
            .args
            .iter()
            .any(|base| match self.names.binding(base, &HashSet::new()) {
                Binding::Builtin { .. } => false,
                Binding::Imported { target }
                    if target == "typing.Protocol" || target == "typing_extensions.Protocol" =>
                {
                    true
                }
                _ => true,
            })
    }
}

impl<'a> Visitor<'a> for Declarations<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let (name, class, function) = match stmt {
            Stmt::ClassDef(node) => (
                Some(&*node.name.id),
                Some(self.may_declare(node)),
                self.in_function,
            ),
            Stmt::FunctionDef(node) => {
                if self.class == Some(true)
                    || self.decorator_is_unread(node)
                    || self.binders.count(&node.name.id) != Some(1)
                {
                    self.found.insert(format!("{}.{}", self.owner, node.name));
                }
                (Some(&*node.name.id), None, true)
            }
            _ => {
                visitor::walk_stmt(self, stmt);
                return;
            }
        };
        let old_class = std::mem::replace(&mut self.class, class);
        let old_function = std::mem::replace(&mut self.in_function, function);
        let length = str::len(&self.owner);
        if let Some(name) = name {
            self.owner.push('.');
            self.owner.push_str(name);
        }
        visitor::walk_stmt(self, stmt);
        self.owner.truncate(length);
        self.class = old_class;
        self.in_function = old_function;
    }
}
