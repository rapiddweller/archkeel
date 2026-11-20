// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read written typing positions, dynamic calls and the Any annotation inventory.

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Alias, Expr, ExprAttribute, ExprContext, Stmt, StmtClassDef};
use ruff_text_size::{Ranged, TextSize};
use std::collections::HashMap;

use super::binders::Binders;
use super::class_writes::{future_annotations, ClassWrites};
use crate::module::Module;

pub(super) fn count(module: &Module, binders: &Binders) -> (u64, u64) {
    let unique = binders.unique();
    let imported: std::collections::HashSet<String> = module
        .tree
        .body
        .iter()
        .filter(|stmt| matches!(stmt, Stmt::Import(_)))
        .flat_map(crate::module::import_bindings)
        .filter(|name| unique.contains(name))
        .collect();
    let casts = module
        .tree
        .body
        .iter()
        .filter_map(|stmt| match stmt {
            Stmt::ImportFrom(node)
                if node
                    .module
                    .as_ref()
                    .is_some_and(|name| name.as_str() == "typing")
                    && node.level == 0 =>
            {
                Some(&node.names)
            }
            _ => None,
        })
        .flatten()
        .filter(|alias| alias.name.as_str() == "cast")
        .map(|alias| {
            alias
                .asname
                .as_ref()
                .unwrap_or(&alias.name)
                .as_str()
                .to_owned()
        })
        .collect();
    let typing_modules = module
        .tree
        .body
        .iter()
        .filter_map(|stmt| match stmt {
            Stmt::Import(node) => Some(&node.names),
            _ => None,
        })
        .flatten()
        .filter(|alias| alias.name.as_str() == "typing")
        .map(|alias| {
            alias
                .asname
                .as_ref()
                .unwrap_or(&alias.name)
                .as_str()
                .to_owned()
        })
        .collect();
    let mut walk = Typing {
        imported,
        casts,
        typing_modules,
        count: 0,
        private: 0,
        public: true,
        class: false,
        method: false,
        receiver: None,
        method_body: None,
    };
    walk.visit_body(&module.tree.body);
    (walk.count, walk.private)
}

struct Typing {
    imported: std::collections::HashSet<String>,
    casts: std::collections::HashSet<String>,
    typing_modules: std::collections::HashSet<String>,
    count: u64,
    private: u64,
    public: bool,
    class: bool,
    method: bool,
    receiver: Option<String>,
    method_body: Option<(TextSize, TextSize)>,
}

impl<'a> Visitor<'a> for Typing {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        let before = self.public;
        let old_class = self.class;
        let old_method = self.method;
        let old_receiver = self.receiver.clone();
        let old_body = self.method_body;
        match stmt {
            Stmt::FunctionDef(node) => {
                self.method = self.class;
                self.class = false;
                self.receiver = node
                    .parameters
                    .posonlyargs
                    .first()
                    .or_else(|| node.parameters.args.first())
                    .map(|arg| arg.parameter.name.as_str())
                    .filter(|name| {
                        self.method
                            && node.decorator_list.is_empty()
                            && matches!(*name, "self" | "cls")
                    })
                    .map(str::to_owned);
                self.method_body = node
                    .body
                    .first()
                    .zip(node.body.last())
                    .map(|(first, last)| (first.start(), last.end()));
                self.public &= !node.name.as_str().starts_with('_');
                let all = node.parameters.iter().map(|arg| arg.as_parameter());
                let receiver = self.receiver.clone();
                for (_, parameter) in all.enumerate().filter(|(index, parameter)| {
                    !(*index == 0 && receiver.as_deref() == Some(parameter.name.as_str()))
                }) {
                    self.count += position(parameter.annotation.as_deref(), self.public);
                }
                self.count += position(node.returns.as_deref(), self.public);
            }
            Stmt::ClassDef(node) => {
                self.public &= !node.name.as_str().starts_with('_');
                self.class = true;
                self.method = false;
                self.receiver = None;
                self.method_body = None;
            }
            Stmt::AugAssign(node) => {
                if let Expr::Attribute(attr) = &*node.target {
                    self.private += u64::from(self.private_read(attr));
                }
            }
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
        self.public = before;
        self.class = old_class;
        self.method = old_method;
        self.receiver = old_receiver;
        self.method_body = old_body;
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Attribute(attr) = expr {
            if attr.ctx == ExprContext::Load {
                self.private += u64::from(self.private_read(attr));
            }
        }
        let callee = match expr {
            Expr::Call(call) => match &*call.func {
                Expr::Name(name) => Some(name.id.as_str()),
                _ => None,
            },
            _ => None,
        };
        if let Some(name) = callee {
            self.count +=
                u64::from(matches!(name, "getattr" | "eval" | "exec") || self.casts.contains(name));
        }
        if let Expr::Call(call) = expr {
            let typing_cast = matches!(&*call.func, Expr::Attribute(attr)
                if attr.attr.as_str() == "cast" && matches!(&*attr.value, Expr::Name(name)
                    if self.typing_modules.contains(name.id.as_str())));
            self.count += u64::from(typing_cast);
        }
        visitor::walk_expr(self, expr);
    }
}

impl Typing {
    fn private_read(&self, attr: &ExprAttribute) -> bool {
        let exempt = matches!(&*attr.value, Expr::Name(name)
            if (self.receiver.as_deref() == Some(name.id.as_str())
                && self.method_body.is_some_and(|(start, end)| start <= attr.start() && attr.end() <= end))
            || self.imported.contains(name.id.as_str()));
        attr.attr.as_str().starts_with('_') && !exempt
    }
}

fn position(annotation: Option<&Expr>, public: bool) -> u64 {
    let Some(annotation) = annotation else {
        return u64::from(public);
    };
    if let Expr::StringLiteral(text) = annotation {
        return u64::from(
            text.value
                .to_str()
                .split(|ch: char| !ch.is_alphanumeric() && ch != '_')
                .any(|name| matches!(name, "object" | "Any")),
        );
    }
    let mut scan = Untyped(false);
    scan.visit_expr(annotation);
    u64::from(scan.0)
}

struct Untyped(bool);
impl<'a> Visitor<'a> for Untyped {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if let Expr::Name(name) = expr {
            self.0 |= matches!(name.id.as_str(), "object" | "Any") && name.ctx == ExprContext::Load;
        }
        if let Expr::Attribute(attribute) = expr {
            self.0 |= matches!(attribute.attr.as_str(), "object" | "Any");
        }
        visitor::walk_expr(self, expr);
    }
}

struct Source<'a> {
    module: &'a Module,
    binders: &'a Binders,
    imports: HashMap<&'a str, (&'a str, &'a str)>,
    classes: HashMap<&'a str, &'a StmtClassDef>,
}

pub(super) fn any_complete(
    (modules, binders): (&[Module], &[Binders]),
    writes: &ClassWrites,
    comments: impl Fn(&str) -> Vec<std::ops::Range<usize>>,
) -> bool {
    if !writes.annotation_classes_unchanged() {
        return false;
    }
    let sources: HashMap<&str, Source<'_>> = modules
        .iter()
        .zip(binders)
        .map(|(module, binders)| (module.name.as_str(), Source::of(module, binders)))
        .collect();
    let proof = Proof { sources, writes };
    HashMap::values(&proof.sources).all(|source| {
        let module = source.module;
        let text = Module::text(module);
        let mut walk = AnyWalk {
            proof: &proof,
            source,
            complete: true,
        };
        walk.visit_body(&module.tree.body);
        walk.complete
            && Binders::count(source.binders, "__getattr__") == Some(0)
            && !comments(text)
                .into_iter()
                .any(|range| type_comment(&text[range]))
    })
}

impl<'a> Source<'a> {
    fn of(module: &'a Module, binders: &'a Binders) -> Self {
        let body = &module.tree.body;
        let checked = future_annotations(&module.tree)
            && body
                .iter()
                .filter_map(import_from)
                .any(|(target, aliases)| {
                    target == "typing"
                        && aliases.iter().any(|alias| {
                            alias.name.as_str() == "TYPE_CHECKING"
                                && alias.asname.is_none()
                                && binders.count("TYPE_CHECKING") == Some(1)
                        })
                });
        let imports = body
            .iter()
            .flat_map(|stmt| match stmt {
                Stmt::If(node)
                    if checked
                        && matches!(&*node.test,
                    Expr::Name(name) if name.id.as_str() == "TYPE_CHECKING") =>
                {
                    node.body.as_slice()
                }
                _ => std::slice::from_ref(stmt),
            })
            .filter_map(import_from)
            .flat_map(|(target, aliases)| aliases.iter().map(move |alias| (target, alias)))
            .filter_map(|(target, alias)| {
                let name = alias.asname.as_ref().unwrap_or(&alias.name).as_str();
                (binders.count(name) == Some(1)).then_some((name, (target, alias.name.as_str())))
            })
            .collect();
        let classes = body
            .iter()
            .filter_map(|stmt| match stmt {
                Stmt::ClassDef(class) if binders.count(class.name.as_str()) == Some(1) => {
                    Some((class.name.as_str(), class))
                }
                _ => None,
            })
            .collect();
        Self {
            module,
            binders,
            imports,
            classes,
        }
    }
}

fn import_from(stmt: &Stmt) -> Option<(&str, &[Alias])> {
    match stmt {
        Stmt::ImportFrom(node) if node.level == 0 => {
            Some((node.module.as_ref()?.as_str(), &node.names))
        }
        _ => None,
    }
}

struct Proof<'a> {
    sources: HashMap<&'a str, Source<'a>>,
    writes: &'a ClassWrites,
}

impl Proof<'_> {
    fn type_name(&self, source: &Source<'_>, name: &str) -> bool {
        let mut source = source;
        let mut name = name;
        for hop in 0..32 {
            // Python injects dunder names and can bind a mangled spelling in a class.
            if name.contains("__") || ClassWrites::change_of(self.writes, name).is_some() {
                return false;
            }
            if hop == 0 && builtin(name) && Binders::builtin_visible(source.binders, name) {
                return true;
            }
            if let Some(class) = HashMap::get(&source.classes, name) {
                return self.class_is_type(source, class);
            }
            let Some(&(target, symbol)) = HashMap::get(&source.imports, name) else {
                return false;
            };
            match HashMap::get(&self.sources, target) {
                Some(next) => {
                    source = next;
                    name = symbol;
                }
                None => {
                    return (target, symbol) == ("pathlib", "Path")
                        && !ClassWrites::shadows(self.writes, "pathlib")
                        && ClassWrites::change_of(self.writes, "Path").is_none();
                }
            }
        }
        false
    }

    fn visible_builtin(&self, source: &Source<'_>, name: &str) -> bool {
        Binders::builtin_visible(source.binders, name)
            && ClassWrites::change_of(self.writes, name).is_none()
    }

    fn annotation(&self, source: &Source<'_>, expr: &Expr) -> bool {
        match expr {
            Expr::Name(node) => self.type_name(source, node.id.as_str()),
            Expr::NoneLiteral(_) | Expr::EllipsisLiteral(_) => true,
            Expr::Tuple(node) => node.elts.iter().all(|item| self.annotation(source, item)),
            Expr::Subscript(node) => {
                matches!(&*node.value, Expr::Name(name)
                    if matches!(name.id.as_str(), "dict" | "frozenset" | "list" | "set" | "tuple")
                        && self.visible_builtin(source, name.id.as_str()))
                    && self.annotation(source, &node.slice)
            }
            _ => false,
        }
    }
    fn class_is_type(&self, source: &Source<'_>, class: &StmtClassDef) -> bool {
        if class.type_params.is_some() {
            return false;
        }
        let imported = |expr: &Expr| match expr {
            Expr::Name(name) => {
                let (module, symbol) = HashMap::get(&source.imports, name.id.as_str()).copied()?;
                (!HashMap::contains_key(&self.sources, module)
                    && !ClassWrites::shadows(self.writes, module)
                    && ClassWrites::change_of(self.writes, symbol).is_none())
                .then_some((module, symbol))
            }
            _ => None,
        };
        match &*class.decorator_list {
            [] => class.arguments.as_ref().is_none_or(|args| {
                args.keywords.is_empty()
                    && match &*args.args {
                        [] => true,
                        [base] => matches!(
                            imported(base),
                            Some(("typing", "Protocol" | "TypedDict") | ("enum", "StrEnum"))
                        ),
                        _ => false,
                    }
            }),
            [decorator] if class.arguments.is_none() => {
                matches!(&decorator.expression, Expr::Call(call)
                if imported(&call.func) == Some(("dataclasses", "dataclass"))
                    && call.arguments.args.is_empty()
                    && call.arguments.keywords.iter().all(|kw|
                        kw.arg.as_ref().is_some_and(|name| matches!(name.as_str(), "frozen" | "slots"))
                            && matches!(kw.value, Expr::BooleanLiteral(_))))
            }
            _ => false,
        }
    }
}

fn builtin(name: &str) -> bool {
    const TYPES: [&str; 11] = [
        "bool",
        "bytes",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "object",
        "set",
        "str",
        "tuple",
    ];
    TYPES.contains(&name)
}

struct AnyWalk<'a> {
    proof: &'a Proof<'a>,
    source: &'a Source<'a>,
    complete: bool,
}

impl<'a> Visitor<'a> for AnyWalk<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        self.complete &= match stmt {
            Stmt::ClassDef(class) => self.proof.class_is_type(self.source, class),
            Stmt::TypeAlias(_) => false,
            Stmt::FunctionDef(node) => node.type_params.is_none(),
            _ => true,
        };
        if self.complete {
            visitor::walk_stmt(self, stmt);
        }
    }

    fn visit_annotation(&mut self, expr: &'a Expr) {
        self.complete &= self.proof.annotation(self.source, expr);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        self.complete &= !matches!(expr, Expr::Name(name) if name.id.as_str() == "Any")
            && !matches!(expr, Expr::Attribute(attr) if attr.attr.as_str() == "Any");
        visitor::walk_expr(self, expr);
    }

    fn visit_alias(&mut self, alias: &'a Alias) {
        self.complete &= !matches!(alias.name.as_str(), "Any" | "*");
    }
}

fn type_comment(text: &str) -> bool {
    let body = text.strip_prefix('#').unwrap_or(text).trim_start();
    body.strip_prefix("type:").is_some_and(|body| {
        let body = body.trim();
        body != "ignore" && !body.starts_with("ignore[")
    })
}

#[cfg(test)]
#[path = "typing_count_tests.rs"]
mod tests;
