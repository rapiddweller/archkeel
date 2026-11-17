// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bounded inert reads of imported door modules (AD-574). The import gap stays.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Expr, ExprCall, ModModule, Stmt};

pub(super) fn code_type_check(call: &ExprCall, types: &HashSet<String>, visible: bool) -> bool {
    visible
        && matches!(&*call.func, Expr::Name(name) if name.id.as_str() == "isinstance")
        && call.arguments.args.len() == 2
        && call.arguments.keywords.is_empty()
        && matches!(&call.arguments.args[1], Expr::Name(name) if types.contains(name.id.as_str()))
}

pub(super) fn code_types(
    bound: &HashMap<String, Vec<String>>,
    unique: &HashSet<String>,
) -> HashSet<String> {
    ["FunctionType", "CodeType"]
        .into_iter()
        .filter(|name| {
            unique.contains(*name)
                && bound
                    .get(*name)
                    .is_some_and(|origins| origins.as_slice() == [format!("types.{name}")])
        })
        .map(str::to_owned)
        .collect()
}

pub(super) fn modules(
    bound: &HashMap<String, Vec<String>>,
    unique: &HashSet<String>,
    tree: &ModModule,
) -> HashMap<String, String> {
    let mut modules: HashMap<String, String> = bound
        .iter()
        .filter_map(|(name, origins)| match origins.as_slice() {
            [origin]
                if unique.contains(name)
                    && (matches!(
                        origin.as_str(),
                        "pickle" | "dill" | "importlib.metadata" | "importlib.abc"
                    ) || super::names::hazard(origin).is_some()
                        && origin
                            .rsplit_once('.')
                            .is_some_and(|(module, attr)| attribute(module, attr))) =>
            {
                Some((name.clone(), origin.clone()))
            }
            _ => None,
        })
        .collect();
    if unique.contains("importlib")
        && tree.body.iter().any(|stmt| {
            matches!(stmt, Stmt::Import(node)
            if node.names.iter().any(|alias| alias.name.as_str() == "importlib.metadata"
                && alias.asname.is_none()))
        })
    {
        modules.insert("importlib".to_owned(), "importlib".to_owned());
    }
    modules
}

pub(super) fn read(modules: &HashMap<String, String>, name: &str, attrs: &[&str]) -> bool {
    modules.get(name).is_some_and(|module| match attrs {
        [attr] => attribute(module, attr),
        [] => module
            .rsplit_once('.')
            .is_some_and(|(parent, attr)| attribute(parent, attr)),
        ["metadata", attr] if module == "importlib" => attribute("importlib.metadata", attr),
        _ => false,
    })
}

fn attribute(module: &str, attr: &str) -> bool {
    matches!(
        (module, attr),
        (
            "pickle",
            "UnpicklingError" | "PickleError" | "HIGHEST_PROTOCOL"
        ) | (
            "importlib.metadata",
            "PackageNotFoundError" | "version" | "distribution" | "distributions"
        ) | ("importlib.abc", "Traversable")
            | ("dill", "settings")
    )
}
