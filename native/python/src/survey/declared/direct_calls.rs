// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The direct instance method of a fresh Python object (AD-1027).

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::ConstructedCall;
use archkeel_facts::ids::{FactId, ModuleName};
use archkeel_facts::nullable::Nullable;
use archkeel_facts::vocab::{MethodKind, Status};
use archkeel_facts::{CallFact, ImportFact, Record, SymbolFact};
use ruff_python_ast::{Expr, ExprCall, Stmt, StmtFunctionDef};

use super::found::Found;
use crate::module::Module;
use crate::survey::class_writes::{may_write, ClassWrites};

pub(crate) struct DirectMethods {
    methods: HashMap<String, HashMap<String, FactId>>,
    imports: HashMap<String, HashMap<String, (String, FactId)>>,
}

impl DirectMethods {
    pub(crate) fn empty() -> Self {
        Self {
            methods: HashMap::new(),
            imports: HashMap::new(),
        }
    }

    pub(crate) fn of(
        found: &[Found<'_>],
        modules: &[Module],
        writes: &ClassWrites,
        imports: &[Record<ImportFact>],
    ) -> Self {
        let mut methods = HashMap::new();
        let mut direct = HashMap::new();
        let hooks = [
            "__bases__",
            "__class__",
            "__new__",
            "__init__",
            "__getattribute__",
            "__getattr__",
            "__setattr__",
            "__delattr__",
        ];
        if hooks.into_iter().any(|name| may_write(writes, name)) {
            return Self::empty();
        }
        for declarations in found {
            let module = &modules[declarations.index];
            let plain: HashSet<_> = module.tree.body.iter().filter_map(plain_class).collect();
            let eligible = declarations.records.iter().filter_map(|record| {
                target(
                    record,
                    &declarations.constructible,
                    (&module.name, &plain),
                    writes,
                )
            });
            for (class, member, id) in eligible {
                HashMap::entry(&mut methods, class.to_owned())
                    .or_insert_with(HashMap::new)
                    .insert(member.to_owned(), id.clone());
            }
        }
        let bound_imports = imports.iter().filter_map(|record| {
            let ImportFact::Import(data) = &record.data else {
                return None;
            };
            archkeel_facts::data::ImportData::direct_symbol_route(data)
                .map(|route| (route, &record.id))
        });
        for ([source, provider, symbol, bound], id) in bound_imports {
            let class = format!("{provider}.{symbol}");
            if HashMap::contains_key(&methods, &class) {
                HashMap::entry(&mut direct, source.to_owned())
                    .or_insert_with(HashMap::new)
                    .insert(bound.to_owned(), (class, id.clone()));
            }
        }
        Self {
            methods,
            imports: direct,
        }
    }

    pub(crate) fn targets(&self) -> Vec<FactId> {
        let mut ids: Vec<_> = self
            .methods
            .values()
            .flat_map(|methods| methods.values().cloned())
            .collect();
        ids.sort_unstable();
        ids
    }

    pub(super) fn witness(
        &self,
        source: &StmtFunctionDef,
        records: &[Record<CallFact>],
        sites: &[(&ExprCall, bool)],
    ) -> Option<ConstructedCall> {
        let (method, constructor, local, name) = pair(source)?;
        let index = |node: &ExprCall| {
            sites
                .iter()
                .position(|(site, dead)| !dead && std::ptr::eq(*site, node))
        };
        let constructor = records.get(index(constructor)?)?;
        let CallFact::Calls(data) = &constructor.data else {
            return None;
        };
        let Nullable::Value(allocation) = &data.construction else {
            return None;
        };
        let [class] = Vec::as_slice(&allocation.targets) else {
            return None;
        };
        if allocation.status != Status::Resolved {
            return None;
        }
        let binding = match local {
            Some(name) => Some(
                data.result_bindings
                    .as_deref()?
                    .iter()
                    .find(|item| item.name == name)?
                    .id
                    .clone(),
            ),
            None => None,
        };
        let method_id = self.methods.get(class)?.get(name)?.clone();
        let (provider, _) = class.rsplit_once('.')?;
        let source = ModuleName::as_str(&data.source_module);
        let import = if source == provider {
            None
        } else {
            let (target, id) = self.imports.get(source)?.get(&data.expression)?;
            if target != class {
                return None;
            }
            Some(id.clone())
        };
        let constructor_id = constructor.id.clone();
        let call = records.get(index(method)?)?;
        Some(ConstructedCall {
            call: call.id.clone(),
            constructor: constructor_id,
            method: method_id,
            binding,
            import,
        })
    }
}

fn target<'a>(
    record: &'a Record<SymbolFact>,
    constructible: &HashSet<String>,
    (module, plain): (&str, &HashSet<&str>),
    writes: &ClassWrites,
) -> Option<(&'a str, &'a str, &'a FactId)> {
    let SymbolFact::Method(data) = &record.data else {
        return None;
    };
    let class = data.parent.as_deref()?;
    let name = class.strip_prefix(module)?.strip_prefix('.')?;
    (data.method_kind == Some(MethodKind::Instance)
        && !may_write(writes, &data.name)
        && HashSet::contains(constructible, class)
        && HashSet::contains(plain, name)
        && !may_write(writes, name))
    .then_some((class, &data.name, &record.id))
}

fn plain_class(stmt: &Stmt) -> Option<&str> {
    let Stmt::ClassDef(class) = stmt else {
        return None;
    };
    (class.arguments.is_none()
        && class.type_params.is_none()
        && Vec::is_empty(&class.decorator_list)
        && class.body.iter().all(|stmt| match stmt {
            Stmt::FunctionDef(method) => {
                !method.name.as_str().starts_with("__")
                    && Vec::is_empty(&method.decorator_list)
                    && method.type_params.is_none()
                    && method.returns.is_none()
                    && method
                        .parameters
                        .posonlyargs
                        .iter()
                        .chain(&method.parameters.args)
                        .chain(&method.parameters.kwonlyargs)
                        .all(|item| item.default.is_none() && item.parameter.annotation.is_none())
                    && method.parameters.vararg.is_none()
                    && method.parameters.kwarg.is_none()
            }
            Stmt::Pass(_) => true,
            Stmt::Expr(stmt) => matches!(&*stmt.value, Expr::StringLiteral(_)),
            _ => false,
        }))
    .then_some(class.name.as_str())
}

/// There is no user code between the two operations that can replace the receiver.
fn pair(source: &StmtFunctionDef) -> Option<(&ExprCall, &ExprCall, Option<&str>, &str)> {
    let (returned, binding) = match source.body.as_slice() {
        [Stmt::Return(returned)] => (returned, None),
        [Stmt::Assign(assign), Stmt::Return(returned)] => {
            let [Expr::Name(local)] = assign.targets.as_slice() else {
                return None;
            };
            let Expr::Call(call) = &*assign.value else {
                return None;
            };
            (returned, Some((local.id.as_str(), call)))
        }
        _ => return None,
    };
    let Expr::Call(method) = returned.value.as_deref()? else {
        return None;
    };
    let Expr::Attribute(member) = &*method.func else {
        return None;
    };
    let (constructor, local) = match (&*member.value, binding) {
        (Expr::Call(call), None) => (call, None),
        (Expr::Name(receiver), Some((name, call))) if receiver.id.as_str() == name => {
            (call, Some(name))
        }
        _ => return None,
    };
    (method.arguments.is_empty()
        && constructor.arguments.is_empty()
        && matches!(&*constructor.func, Expr::Name(_)))
    .then_some((method, constructor, local, member.attr.as_str()))
}
