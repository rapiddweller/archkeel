// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the imports of a module say for the annotation rules (AD-1173): evaluators and builders
//! under another name, and names that come from the standard library.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::{Alias, Expr};

use super::forms::last;

pub(super) const EVALUATORS: [&str; 5] = [
    "get_type_hints",
    "get_annotations",
    "ForwardRef",
    "_eval_type",
    "evaluate_forward_ref",
];
const STANDARD: [&str; 4] = ["typing", "typing_extensions", "enum", "collections"];

pub(super) struct Imports {
    /// The module names an evaluator.
    pub(super) evaluates: bool,
    /// `import a as b` and `B = a`: `b` is `a`.
    pub(super) aliases: HashMap<String, String>,
    /// A local name that the module imports from `typing`, `enum` or `collections`: local -> real.
    names: HashMap<String, String>,
    modules: HashSet<String>,
}

impl Imports {
    pub(super) fn new() -> Self {
        Self {
            evaluates: false,
            aliases: HashMap::new(),
            names: HashMap::new(),
            modules: HashSet::new(),
        }
    }

    pub(super) fn add(&mut self, module: Option<&str>, aliases: &[Alias]) {
        for alias in aliases {
            let name = alias.name.rsplit('.').next().unwrap_or_default();
            self.evaluates |= EVALUATORS.contains(&name);
            let local = alias.asname.as_ref().unwrap_or(&alias.name).to_string();
            if let Some(local) = &alias.asname {
                self.aliases.insert(local.to_string(), name.to_owned());
            }
            match module {
                Some(module) if STANDARD.contains(&module) => {
                    self.names.insert(local, alias.name.to_string());
                }
                None if STANDARD.contains(&alias.name.as_str()) => {
                    self.modules.insert(local);
                }
                _ => {}
            }
        }
    }

    /// The name that `local` stands for through an import or an assignment.
    pub(super) fn real<'a>(&'a self, local: &'a str) -> &'a str {
        self.aliases.get(local).map_or(local, String::as_str)
    }

    /// The real name of a callee that the module imports from the standard library.
    pub(super) fn standard<'a>(&'a self, callee: &'a Expr) -> Option<&'a str> {
        match callee {
            Expr::Name(node) => self.names.get(node.id.as_str()).map(String::as_str),
            Expr::Attribute(node) => match &*node.value {
                Expr::Name(root) if self.modules.contains(root.id.as_str()) => last(callee),
                _ => None,
            },
            _ => None,
        }
    }
}
