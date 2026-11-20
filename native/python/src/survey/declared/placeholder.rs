// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Methods whose class may be a declaration rather than an implementation.

use std::collections::{HashMap, HashSet};

use archkeel_facts::ids::{ModuleName, PackageName};
use archkeel_facts::type_shape::Binding;
use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Expr, Stmt, StmtClassDef, StmtFunctionDef};
use ruff_text_size::{Ranged, TextSize};

use super::shape_names::{Hidden, Names};
use crate::module::Module;
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;
use crate::survey::class_writes::ClassWrites;
use crate::survey::support::PlaceholderDecision as Decision;

pub(in crate::survey) fn standard_protocol(
    modules: &[Module],
    imports: &[Record<ImportFact>],
    stdlib: &HashSet<&str>,
    writes: &ClassWrites,
) -> bool {
    let owned: HashSet<&str> = modules
        .iter()
        .map(|module| String::as_str(&module.name))
        .collect();
    stdlib.contains("typing")
        && writes.typing_holds("Protocol")
        && [
            "_ProtocolMeta",
            "_is_protocol",
            "__new__",
            "__init_subclass__",
        ]
        .into_iter()
        .all(|name| Option::is_none(&writes.change_of(name)))
        && imports.iter().all(|record| {
            let data = ImportFact::data(&record.data);
            owned.contains(ModuleName::as_str(&data.target_module))
                || (stdlib.contains(PackageName::as_str(&data.target_package))
                    && !writes.shadows(PackageName::as_str(&data.target_package)))
        })
}

pub(in crate::survey) fn decisions(
    module: &Module,
    binders: &Binders,
    imports: &[&Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
    protocol_unchanged: bool,
) -> HashMap<TextSize, Decision> {
    let names = Names::of((&module.name, &module.tree), binders, imports, sets);
    let mut walk = Declarations {
        names: &names,
        binders,
        module,
        module_bound: Bound::of(&module.tree.body),
        protocol_unchanged,
        class: None,
        in_function: false,
        found: HashMap::new(),
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
    module: &'a Module,
    module_bound: Bound,
    protocol_unchanged: bool,
    class: Option<ClassBody>,
    in_function: bool,
    found: HashMap<TextSize, Decision>,
}

enum ClassBody {
    Protocol(Box<Bound>),
    Implementation,
    Unread,
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

    fn class_body(&self, node: &StmtClassDef) -> ClassBody {
        if !matches!(node.decorator_list.as_slice(), []) {
            return ClassBody::Unread;
        }
        let Some(arguments) = &node.arguments else {
            return ClassBody::Implementation;
        };
        if !matches!(arguments.keywords.as_slice(), [])
            || (!matches!(arguments.args.as_slice(), [])
                && (self.class.is_some() || self.in_function))
        {
            return ClassBody::Unread;
        }
        if let [base] = arguments.args.as_ref() {
            if self.protocol_base(node, base) {
                return ClassBody::Protocol(Box::new(Bound::of(&node.body)));
            }
        }
        if arguments.args.iter().all(|base| {
            matches!(
                self.names.binding(base, &Hidden::default()),
                Binding::Builtin { .. }
            )
        }) {
            ClassBody::Implementation
        } else {
            ClassBody::Unread
        }
    }

    fn protocol_base(&self, node: &StmtClassDef, base: &Expr) -> bool {
        self.protocol_unchanged
            && node.type_params.is_none()
            && self.module_bound.sole(
                ruff_python_ast::name::Name::as_str(&node.name.id),
                node.start(),
            )
            && matches!(
                self.names.binding(base, &Hidden::default()),
                Binding::Imported { target } if target == "typing.Protocol"
            )
            && self
                .module
                .tree
                .body
                .iter()
                .take_while(|stmt| stmt.start() < node.start())
                .any(|stmt| imports_base(stmt, base))
    }

    fn decision(&self, node: &StmtFunctionDef) -> Option<Decision> {
        if let Some(ClassBody::Protocol(body)) = &self.class {
            let proven = matches!(node.decorator_list.as_slice(), [])
                && body.sole(
                    ruff_python_ast::name::Name::as_str(&node.name.id),
                    node.start(),
                )
                && body.unbound("_is_protocol");
            return Some(if proven {
                Decision::Declaration
            } else {
                Decision::Unread
            });
        }
        (matches!(self.class, Some(ClassBody::Unread))
            || self.decorator_is_unread(node)
            || self.binders.count(&node.name.id) != Some(1))
        .then_some(Decision::Unread)
    }
}

fn imports_base(stmt: &Stmt, base: &Expr) -> bool {
    let (aliases, imported, binding) = match (stmt, base) {
        (Stmt::ImportFrom(stmt), Expr::Name(name))
            if stmt.level == 0
                && stmt
                    .module
                    .as_ref()
                    .is_some_and(|name| ruff_python_ast::Identifier::as_str(name) == "typing") =>
        {
            (
                &stmt.names,
                "Protocol",
                ruff_python_ast::name::Name::as_str(&name.id),
            )
        }
        (Stmt::Import(stmt), Expr::Attribute(attr))
            if ruff_python_ast::Identifier::as_str(&attr.attr) == "Protocol" =>
        {
            let Expr::Name(name) = attr.value.as_ref() else {
                return false;
            };
            (
                &stmt.names,
                "typing",
                ruff_python_ast::name::Name::as_str(&name.id),
            )
        }
        _ => return false,
    };
    aliases.iter().any(|alias| {
        ruff_python_ast::Identifier::as_str(&alias.name) == imported
            && ruff_python_ast::Identifier::as_str(alias.asname.as_ref().unwrap_or(&alias.name))
                == binding
    })
}

impl<'a> Visitor<'a> for Declarations<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let (class, function) = match stmt {
            Stmt::ClassDef(node) => (Some(self.class_body(node)), self.in_function),
            Stmt::FunctionDef(node) => {
                if let Some(decision) = self.decision(node) {
                    self.found.insert(node.start(), decision);
                }
                (None, true)
            }
            _ => {
                visitor::walk_stmt(self, stmt);
                return;
            }
        };
        let old_class = std::mem::replace(&mut self.class, class);
        let old_function = std::mem::replace(&mut self.in_function, function);
        visitor::walk_stmt(self, stmt);
        self.class = old_class;
        self.in_function = old_function;
    }
}
