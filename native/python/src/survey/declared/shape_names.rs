// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The binding of a name in a written type (AD-550): what the module binds it to, by the binder
//! rules of AD-504 and AD-518, never by its spelling.
//!
//! A name is proven when it is a builtin that no statement of the module hides, or when exactly one
//! plain statement of the module body binds it: a `def`, a `class`, a value, or one plain import.
//! Any other name carries the cause that stopped the proof, and the model reads it as a named gap.

use std::collections::{HashMap, HashSet};

use archkeel_facts::type_shape::{Binding, Unproven};
use archkeel_facts::{ImportFact, Record};
use ruff_python_ast::{Expr, ModModule};

use crate::module::first_part;
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;
use crate::survey::bound_kind::Kind;

/// The builtin classes that a written type can name. Another builtin is a name with no proof.
const BUILTIN_TYPES: [&str; 12] = [
    "int",
    "str",
    "bytes",
    "bool",
    "float",
    "complex",
    "object",
    "dict",
    "list",
    "set",
    "frozenset",
    "tuple",
];

/// What a plain import of the module brings.
enum Import {
    /// `from m import n`: the qualified name `m.n`.
    Name(String),
    /// `import m` or `import m.n as k`: the module object.
    Module(String),
}

/// The bindings of one module body.
pub(super) struct Names<'a> {
    module: &'a str,
    bound: Bound,
    names: HashSet<String>,
    binders: &'a Binders,
    imports: HashMap<String, Import>,
}

impl<'a> Names<'a> {
    /// The bindings of `tree`, with the plain imports of `records` that the survey calls sole.
    pub(super) fn of(
        (module, tree): (&'a str, &ModModule),
        binders: &'a Binders,
        records: &[&Record<ImportFact>],
        (sole, ambiguous): (&HashSet<String>, &HashSet<String>),
    ) -> Self {
        let bound = Bound::of(&tree.body);
        let names = bound.names();
        let mut imports = HashMap::new();
        for record in records {
            let data = record.data.data();
            let id = record.id.as_str();
            if data.source_module.as_str() != module
                || !sole.contains(id)
                || ambiguous.contains(id)
                || data.under_type_checking
                || !data.module_level_import
            {
                continue;
            }
            let Some(binding) = &data.binding else {
                continue;
            };
            let target = data.target_module.as_str();
            let found = match &data.symbol {
                Some(symbol) => Import::Name(format!("{target}.{symbol}")),
                // `import a.b` binds `a`, so only a plain `import a` or an alias names the target.
                None if binding == target || binding != first_part(target) => {
                    Import::Module(target.to_owned())
                }
                None => continue,
            };
            imports.insert(binding.clone(), found);
        }
        Names {
            module,
            bound,
            names,
            binders,
            imports,
        }
    }

    /// The binding of the expression `root` or `root.attribute`, where `hidden` are the names that
    /// the enclosing class body and the type parameters bind.
    pub(super) fn binding(&self, expr: &Expr, hidden: &HashSet<String>) -> Binding {
        match expr {
            Expr::Name(node) => self.name(node.id.as_str(), hidden),
            Expr::Attribute(node) => match &*node.value {
                Expr::Name(root) => self.attribute(root.id.as_str(), node.attr.as_str(), hidden),
                _ => unproven(Unproven::Dotted),
            },
            _ => unproven(Unproven::Dotted),
        }
    }

    fn attribute(&self, root: &str, attribute: &str, hidden: &HashSet<String>) -> Binding {
        match self.name_import(root, hidden) {
            Ok(Import::Module(module)) => Binding::Imported {
                target: format!("{module}.{attribute}"),
            },
            Ok(Import::Name(_)) => unproven(Unproven::Dotted),
            Err(cause) => unproven(cause),
        }
    }

    pub(super) fn name(&self, name: &str, hidden: &HashSet<String>) -> Binding {
        if hidden.contains(name) {
            return unproven(Unproven::Hidden);
        }
        if self.bound.opaque {
            return unproven(Unproven::StarImport);
        }
        match self.bound.kind(name) {
            Some(
                Kind::Callable
                | Kind::Value
                | Kind::BuiltinGeneric(_)
                | Kind::Call
                | Kind::Derived
                | Kind::Other,
            ) => Binding::Defined {
                target: format!("{}.{name}", self.module),
            },
            Some(Kind::Import) => match self.imports.get(name) {
                Some(Import::Name(target)) => Binding::Imported {
                    target: target.clone(),
                },
                _ => unproven(Unproven::UnreadImport),
            },
            None if self.names.contains(name) => unproven(Unproven::NotSole),
            None if BUILTIN_TYPES.contains(&name) && self.binders.builtin_visible(name) => {
                Binding::Builtin {
                    target: name.to_owned(),
                }
            }
            None => unproven(Unproven::Unbound),
        }
    }

    /// The one plain import that `name` reads, or the cause that there is none.
    fn name_import(&self, name: &str, hidden: &HashSet<String>) -> Result<&Import, Unproven> {
        if hidden.contains(name) {
            return Err(Unproven::Hidden);
        }
        if self.bound.opaque {
            return Err(Unproven::StarImport);
        }
        match self.bound.kind(name) {
            Some(Kind::Import) => self.imports.get(name).ok_or(Unproven::UnreadImport),
            None if self.names.contains(name) => Err(Unproven::NotSole),
            Some(_) => Err(Unproven::Dotted),
            None => Err(Unproven::Unbound),
        }
    }
}

fn unproven(cause: Unproven) -> Binding {
    Binding::Unproven { cause }
}

#[cfg(test)]
mod tests {
    use archkeel_facts::type_shape::{Binding, Unproven};
    use ruff_python_ast::Expr;
    use std::collections::HashSet;

    use super::Names;
    use crate::survey::binders::Binders;

    fn binding_of(source: &str, name: &str) -> Binding {
        let module = crate::test_module(source, 14);
        let binders = Binders::of(&module.tree);
        let names = Names::of(
            ("app.probe", &module.tree),
            &binders,
            &[],
            (&HashSet::new(), &HashSet::new()),
        );
        let expr: Expr = *ruff_python_parser::parse_expression(name)
            .expect("an expression")
            .into_syntax()
            .body;
        names.binding(&expr, &HashSet::new())
    }

    #[test]
    fn a_star_import_withholds_every_name_also_a_builtin() {
        let cause = Binding::Unproven {
            cause: Unproven::StarImport,
        };
        assert_eq!(binding_of("from x import *\n", "int"), cause);
        assert_eq!(binding_of("from x import *\nclass A: ...\n", "A"), cause);
    }

    #[test]
    fn a_builtin_is_proven_only_when_nothing_binds_it() {
        let proven = Binding::Builtin {
            target: "int".to_owned(),
        };
        assert_eq!(binding_of("class A: ...\n", "int"), proven);
        assert_eq!(
            binding_of("def f():\n    global int\n    int = 1\n", "int"),
            Binding::Unproven {
                cause: Unproven::NotSole
            }
        );
    }

    #[test]
    fn a_name_that_is_no_builtin_class_is_unbound() {
        assert_eq!(
            binding_of("x = 1\n", "len"),
            Binding::Unproven {
                cause: Unproven::Unbound
            }
        );
    }
}
