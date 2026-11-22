// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bounded inert reads of imported trojan horse modules (AD-574). The import gap stays.
//!
//! `cleared` finds the sites that the walk of the hazards reports and that the syntax shows to be
//! no trojan horse (AD-1050). `reflect::Proved::covers` drops them by their range.
//!
//! Each proof names the syntax that closes every use of the value. A name that an import
//! binds is never dropped here: another module can import and use the binding, and the walk does
//! not see that (AD-574 keeps the import gap).
//!
//! - `types.CodeType` and `types.FunctionType` in an annotation, or as the class of `isinstance`: the
//!   class is only stored or compared, not used. This holds for the name form and for the attribute
//!   form on the standard module `types`.
//! - `"text" in sys.modules` with a literal: the membership test calls no code of the key.
//! - `globals().keys()` as the only argument of a pure builtin: a view of the names (text) of one
//!   module.
//! - `s = x.__spec__` in a function, where `s` has only these uses: a test `is None`, a read of
//!   `s.name`, `s.parent`, and `s.submodule_search_locations` as a test or as the argument of a
//!   pure builtin or `pkgutil.walk_packages`.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::helpers::any_over_body;
use ruff_python_ast::name::Name;
use ruff_python_ast::{
    CmpOp, ElifElseClause, ExceptHandler, Expr, ExprCall, ExprContext, Identifier, Keyword,
    ModModule, Operator, Parameters, Stmt, StmtFunctionDef,
};
use ruff_text_size::{Ranged, TextRange};

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
                    ) || crate::survey::hazards_names::hazard(origin).is_some()
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

/// The builtins that the proofs read. A proof needs a name that the module does not shadow.
pub(super) const BUILTINS: [&str; 10] = [
    "isinstance",
    "globals",
    "getattr",
    "setattr",
    "set",
    "sorted",
    "list",
    "tuple",
    "frozenset",
    "len",
];

/// The builtins that read a view of names and keep no code of it.
const PURE: &[&str] = BUILTINS.split_at(4).1;

/// The facts of one module that the proofs read.
struct Facts<'a> {
    single: &'a HashSet<String>,
    visible: &'a HashSet<String>,
    code_types: &'a HashSet<String>,
    declared: HashSet<String>,
    sys: HashSet<String>,
    types: HashSet<String>,
    pkgutil: HashSet<String>,
}

/// The ranges of the sites of the module that are no trojan horse. `bound` is what its imports bind.
pub(super) fn cleared(
    tree: &ModModule,
    bound: &HashMap<String, Vec<String>>,
    names: &(HashSet<String>, HashSet<String>, HashSet<String>),
) -> HashSet<TextRange> {
    let (unique, single, visible) = names;
    let code_types = code_types(bound, unique);
    let stdlib = |module: &str| -> HashSet<String> {
        let own = |(name, origins): (&String, &Vec<String>)| {
            (unique.contains(name) && origins.as_slice() == [module]).then(|| name.clone())
        };
        bound.iter().filter_map(own).collect()
    };
    let mut facts = Facts {
        single,
        visible,
        code_types: &code_types,
        declared: HashSet::new(),
        sys: stdlib("sys"),
        types: stdlib("types"),
        pkgutil: stdlib("pkgutil"),
    };
    declared(&tree.body, &mut facts.declared);
    let mut found = HashSet::new();
    let tests = |expr: &Expr| {
        state_test(&facts, expr, &mut found);
        keys_view(&facts, expr, &mut found);
        class_test(&facts, expr, &mut found);
        false
    };
    any_over_body(&tree.body, tests);
    in_statements(&tree.body, &facts, &mut found);
    found
}

/// The names that a `global` or `nonlocal` statement names, in any function of the module.
fn declared(body: &[Stmt], names: &mut HashSet<String>) {
    for stmt in body {
        let listed: &[Identifier] = match stmt {
            Stmt::Global(node) => &node.names,
            Stmt::Nonlocal(node) => &node.names,
            _ => &[],
        };
        names.extend(
            listed
                .iter()
                .map(|name| Identifier::as_str(name).to_owned()),
        );
        child_bodies(stmt)
            .into_iter()
            .for_each(|inner| declared(inner, names));
    }
}

/// True when the module does not shadow the builtin `name`.
fn visible(facts: &Facts, name: &str) -> bool {
    HashSet::contains(facts.visible, name)
}

/// The name of a plain `Name` expression.
fn name_of(expr: &Expr) -> Option<&str> {
    match expr {
        Expr::Name(node) => Some(Name::as_str(&node.id)),
        _ => None,
    }
}

/// The name `base` of the load `base.attr`.
fn on_name<'e>(expr: &'e Expr, attr: &str) -> Option<&'e str> {
    match expr {
        Expr::Attribute(node) if Identifier::as_str(&node.attr) == attr => {
            name_of(&node.value).filter(|_| node.ctx == ExprContext::Load)
        }
        _ => None,
    }
}

/// `types.CodeType` or `types.FunctionType` on a name that is the standard module `types`.
fn class_attribute(facts: &Facts, expr: &Expr) -> bool {
    let Expr::Attribute(node) = expr else {
        return false;
    };
    let class = matches!(Identifier::as_str(&node.attr), "CodeType" | "FunctionType");
    let types: &HashSet<String> = &facts.types;
    class
        && node.ctx == ExprContext::Load
        && name_of(&node.value).is_some_and(|name| types.contains(name))
}

/// The positional arguments of a call that has no keyword argument.
fn positional(call: &ExprCall) -> Option<&[Expr]> {
    let args: &[Expr] = &call.arguments.args;
    let keywords: &[Keyword] = &call.arguments.keywords;
    keywords.is_empty().then_some(args)
}

/// `isinstance(x, types.CodeType)`: the class is only compared.
fn class_test(facts: &Facts, expr: &Expr, found: &mut HashSet<TextRange>) {
    let Expr::Call(call) = expr else { return };
    let builtin = name_of(&call.func) == Some("isinstance") && visible(facts, "isinstance");
    if let (Some([_, class]), true) = (positional(call), builtin) {
        if class_attribute(facts, class) {
            found.insert(class.range());
        }
    }
}

/// The names of a type expression that are no use of the class.
fn annotation(facts: &Facts, expr: &Expr, found: &mut HashSet<TextRange>) {
    let code_types: &HashSet<String> = facts.code_types;
    if class_attribute(facts, expr) {
        found.insert(expr.range());
    }
    match expr {
        Expr::Name(node) if code_types.contains(Name::as_str(&node.id)) => {
            found.insert(node.range());
        }
        Expr::Subscript(node) => {
            annotation(facts, &node.value, found);
            annotation(facts, &node.slice, found);
        }
        Expr::BinOp(node) if node.op == Operator::BitOr => {
            annotation(facts, &node.left, found);
            annotation(facts, &node.right, found);
        }
        Expr::Tuple(node) => {
            let items: &[Expr] = &node.elts;
            items.iter().for_each(|item| annotation(facts, item, found));
        }
        Expr::List(node) => {
            let items: &[Expr] = &node.elts;
            items.iter().for_each(|item| annotation(facts, item, found));
        }
        _ => {}
    }
}

/// `"text" in sys.modules`.
fn state_test(facts: &Facts, expr: &Expr, found: &mut HashSet<TextRange>) {
    let Expr::Compare(node) = expr else { return };
    let ([op], [left, right]) = (&*node.ops, &*node.operands) else {
        return;
    };
    let member = matches!(op, CmpOp::In | CmpOp::NotIn);
    let sys: &HashSet<String> = &facts.sys;
    let state = on_name(right, "modules").is_some_and(|name| sys.contains(name));
    if member && matches!(left, Expr::StringLiteral(_)) && state {
        found.insert(right.range());
    }
}

/// `pure(globals().keys())`.
fn keys_view(facts: &Facts, expr: &Expr, found: &mut HashSet<TextRange>) {
    let Expr::Call(outer) = expr else { return };
    let builtin = |name: &str| visible(facts, name);
    let pure = name_of(&outer.func).is_some_and(|name| PURE.contains(&name) && builtin(name));
    let Some([Expr::Call(keys)]) = positional(outer) else {
        return;
    };
    let Expr::Attribute(view) = &*keys.func else {
        return;
    };
    let Expr::Call(globals) = &*view.value else {
        return;
    };
    let bare = |call: &ExprCall| positional(call).is_some_and(<[Expr]>::is_empty);
    let named = name_of(&globals.func) == Some("globals") && builtin("globals");
    if pure && Identifier::as_str(&view.attr) == "keys" && bare(keys) && bare(globals) && named {
        found.insert(globals.func.range());
    }
}

/// The annotations and the functions of a body, at any depth of the compound statements.
fn in_statements(body: &[Stmt], facts: &Facts, found: &mut HashSet<TextRange>) {
    for stmt in body {
        match stmt {
            Stmt::FunctionDef(def) => in_function(facts, def, found),
            Stmt::AnnAssign(node) => annotation(facts, &node.annotation, found),
            _ => {}
        }
        for inner in child_bodies(stmt) {
            in_statements(inner, facts, found);
        }
    }
}

/// The annotations of the parameters and of the result, and the spec proof of one function.
fn in_function(facts: &Facts, def: &StmtFunctionDef, found: &mut HashSet<TextRange>) {
    let parameters: &Parameters = &def.parameters;
    let notes = parameters.iter().filter_map(|each| each.annotation());
    for note in notes.chain(def.returns.as_deref()) {
        annotation(facts, note, found);
    }
    spec(facts, def, found);
}

/// The statement lists that a statement holds.
fn child_bodies(stmt: &Stmt) -> Vec<&[Stmt]> {
    match stmt {
        Stmt::FunctionDef(node) => vec![&node.body],
        Stmt::ClassDef(node) => vec![&node.body],
        Stmt::If(node) => {
            let clauses: &[ElifElseClause] = &node.elif_else_clauses;
            let mut found: Vec<&[Stmt]> = vec![&node.body];
            found.extend(clauses.iter().map(|clause| clause.body.as_slice()));
            found
        }
        Stmt::For(node) => vec![&node.body, &node.orelse],
        Stmt::While(node) => vec![&node.body, &node.orelse],
        Stmt::With(node) => vec![&node.body],
        Stmt::Try(node) => {
            let handlers: &[ExceptHandler] = &node.handlers;
            let mut found: Vec<&[Stmt]> = vec![&node.body, &node.orelse, &node.finalbody];
            for ExceptHandler::ExceptHandler(handler) in handlers {
                found.push(&handler.body);
            }
            found
        }
        Stmt::Match(node) => node.cases.iter().map(|case| case.body.as_slice()).collect(),
        _ => Vec::new(),
    }
}

/// `s = x.__spec__` as a statement of the function body, with the uses of `s` as listed above.
fn spec(facts: &Facts, def: &StmtFunctionDef, found: &mut HashSet<TextRange>) {
    for stmt in &def.body {
        let Stmt::Assign(node) = stmt else { continue };
        let ([Expr::Name(target)], Some(_)) =
            (node.targets.as_slice(), on_name(&node.value, "__spec__"))
        else {
            continue;
        };
        let id = Name::as_str(&target.id);
        // One binding in the module, in this function, and no `global` or `nonlocal` for the name.
        let local = facts.single.contains(id) && !facts.declared.contains(id);
        if local && spec_uses(facts, def, id) {
            found.insert(node.value.range());
        }
    }
}

/// True when each load of the name `id` in the function is a use that reads no loader.
fn spec_uses(facts: &Facts, def: &StmtFunctionDef, id: &str) -> bool {
    let mut allowed: HashSet<TextRange> = HashSet::new();
    let is_spec = |expr: &Expr| name_of(expr) == Some(id);
    // `s.submodule_search_locations`, `s.name` or `s.parent`: the range of the name `s`.
    let data = |expr: &Expr, attrs: &[&str]| match expr {
        Expr::Attribute(node) if node.ctx == ExprContext::Load => {
            let wanted = attrs.contains(&Identifier::as_str(&node.attr));
            (is_spec(&node.value) && wanted).then(|| node.value.range())
        }
        _ => None,
    };
    let paths = ["submodule_search_locations"];
    let pure = |name: &str| PURE.contains(&name) && visible(facts, name);
    let reader = |callee: &Expr| match callee {
        Expr::Name(node) => pure(Name::as_str(&node.id)),
        Expr::Attribute(node) => {
            let walk = matches!(
                Identifier::as_str(&node.attr),
                "walk_packages" | "iter_modules"
            );
            let pkgutil: &HashSet<String> = &facts.pkgutil;
            walk && name_of(&node.value).is_some_and(|name| pkgutil.contains(name))
        }
        _ => false,
    };
    let mut ok = true;
    let uses = |expr: &Expr| {
        match expr {
            // A test `... is None` of the name or of its search paths.
            Expr::Compare(node) => {
                let ([op], [left, right]) = (&*node.ops, &*node.operands) else {
                    return false;
                };
                let held = |side: &Expr| {
                    let name = is_spec(side).then(|| side.range());
                    name.or_else(|| data(side, &paths))
                };
                let none = |side: &Expr| matches!(side, Expr::NoneLiteral(_));
                let test = matches!(op, CmpOp::Is | CmpOp::IsNot);
                match (test, held(left), held(right)) {
                    (true, Some(range), _) if none(right) => allowed.insert(range),
                    (true, _, Some(range)) if none(left) => allowed.insert(range),
                    _ => false,
                };
            }
            Expr::Attribute(_) => {
                if let Some(range) = data(expr, &["name", "parent"]) {
                    allowed.insert(range);
                }
            }
            Expr::Call(call) if reader(&call.func) => {
                let args: &[Expr] = &call.arguments.args;
                allowed.extend(args.iter().filter_map(|arg| data(arg, &paths)));
            }
            Expr::Name(node) if is_spec(expr) && node.ctx == ExprContext::Load => {
                ok &= allowed.contains(&node.range());
            }
            _ => {}
        }
        false
    };
    any_over_body(&def.body, uses);
    ok
}
