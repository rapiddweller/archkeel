// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One-step aliases and literal reflection of import-bound module names.
//! `Proved` holds the sites that the scan proves are no door (AD-894).

use std::collections::HashMap;

use std::collections::HashSet;

use ruff_python_ast::name::Name;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{Comprehension, Expr, ExprContext, Identifier, ModModule, Stmt};
use ruff_text_size::{Ranged, TextRange};

use crate::survey::bound_kind::scalar_literal;
use crate::survey::value::assignment_parts;

type Bindings = HashMap<String, Vec<String>>;

pub(super) fn deleted_code(tree: &ModModule) -> bool {
    #[derive(Default)]
    struct Deleted(bool);
    impl<'a> Visitor<'a> for Deleted {
        fn visit_expr(&mut self, expr: &'a Expr) {
            self.0 |= matches!(expr, Expr::Name(node) if node.id.as_str() == "code" && node.ctx == ExprContext::Del);
            visitor::walk_expr(self, expr);
        }
    }
    let mut walk = Deleted::default();
    walk.visit_body(&tree.body);
    walk.0
}

/// Add aliases whose value directly names an imported binding, without following alias chains.
pub(super) fn aliases(tree: &ModModule, imports: &mut Bindings) {
    struct Walk<'a> {
        imports: &'a Bindings,
        aliases: Bindings,
    }
    impl Walk<'_> {
        fn add(&mut self, target: &Expr, value: &Expr) {
            let (Expr::Name(target), Expr::Name(value)) = (target, value) else {
                return;
            };
            if let Some(origins) = self.imports.get(value.id.as_str()) {
                self.aliases
                    .entry(target.id.to_string())
                    .or_default()
                    .extend(origins.clone());
            }
        }
    }
    impl<'a> Visitor<'a> for Walk<'_> {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            match stmt {
                Stmt::Assign(node) => node
                    .targets
                    .iter()
                    .for_each(|target| self.add(target, &node.value)),
                Stmt::AnnAssign(node) => node
                    .value
                    .iter()
                    .for_each(|value| self.add(&node.target, value)),
                _ => {}
            }
            visitor::walk_stmt(self, stmt);
        }
        fn visit_expr(&mut self, expr: &'a Expr) {
            if let Expr::Named(node) = expr {
                self.add(&node.target, &node.value);
            }
            visitor::walk_expr(self, expr);
        }
    }
    let mut walk = Walk {
        imports,
        aliases: Bindings::new(),
    };
    walk.visit_body(&tree.body);
    for (name, origins) in walk.aliases {
        imports.entry(name).or_default().extend(origins);
    }
}

/// A visible imported module, or a direct assignment expression of one.
pub(super) fn module(expr: &Expr, bindings: &Bindings) -> bool {
    match expr {
        Expr::Name(node) => bindings.contains_key(node.id.as_str()),
        Expr::Named(node) => {
            matches!(&*node.value, Expr::Name(name) if bindings.contains_key(name.id.as_str()))
        }
        _ => false,
    }
}

fn text(expr: &Expr, expected: &str) -> bool {
    matches!(expr, Expr::StringLiteral(node) if node.value.to_str() == expected)
}

fn call<'a>(expr: &'a Expr, name: &str) -> Option<&'a [Expr]> {
    let Expr::Call(node) = expr else { return None };
    if !matches!(&*node.func, Expr::Name(id) if id.id.as_str() == name)
        || !node.arguments.keywords.is_empty()
    {
        return None;
    }
    Some(&node.arguments.args)
}

/// The functions and classes of the `code` module that run text (#1520).
const RUNNERS: [&str; 3] = ["interact", "InteractiveConsole", "InteractiveInterpreter"];

/// A runner of the `code` module on a name `code`, on a name that a file assigns from `code` or
/// from an attribute `code` (`c = provider.code`), or on an attribute `code` of any value: the scan
/// cannot prove that the value is not the module, so the call can import any module (#1520).
pub(super) fn runner(base: &Expr, attributes: &[&str], aliases: &HashSet<String>) -> bool {
    attributes.iter().enumerate().any(|(at, name)| {
        let before = match at {
            0 => matches!(base, Expr::Name(root)
                if root.id.as_str() == "code" || aliases.contains(root.id.as_str())),
            _ => attributes[at - 1] == "code",
        };
        before && RUNNERS.contains(name)
    })
}

/// The names that the file assigns from the name `code` or from an attribute `code`, in any scope.
pub(super) fn code_aliases(tree: &ModModule) -> HashSet<String> {
    struct Aliases(HashSet<String>);
    impl<'a> Visitor<'a> for Aliases {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            let (targets, value) = assignment_parts(stmt).unwrap_or_default();
            let code = value.is_some_and(|value| match value {
                Expr::Name(name) => name.id.as_str() == "code",
                Expr::Attribute(node) => node.attr.as_str() == "code",
                _ => false,
            });
            if code {
                let names = targets.into_iter().filter_map(|target| match target {
                    Expr::Name(name) => Some(name.id.to_string()),
                    _ => None,
                });
                self.0.extend(names);
            }
            visitor::walk_stmt(self, stmt);
        }
    }
    let mut found = Aliases(HashSet::new());
    found.visit_body(&tree.body);
    found.0
}

/// `getattr(m, "code")`, `vars(m)["code"]`, or `m.__dict__["code"]`.
pub(super) fn code(expr: &Expr, bindings: &Bindings) -> bool {
    if let Some([base, key]) = call(expr, "getattr") {
        return module(base, bindings) && text(key, "code");
    }
    let Expr::Subscript(node) = expr else {
        return false;
    };
    if !text(&node.slice, "code") {
        return false;
    }
    if let Some([base]) = call(&node.value, "vars") {
        return module(base, bindings);
    }
    matches!(&*node.value, Expr::Attribute(attr) if attr.attr.as_str() == "__dict__" && module(&attr.value, bindings))
}

/// One module for the proof: its tree, its unique direct bindings and its imports.
pub(super) type Item<'a> = (&'a ModModule, HashSet<String>, Bindings);

/// The sites that are no door although a door name appears in them (AD-894). The walk of the
/// hazards reports each site, and `covers` finds it again by its range.
pub(super) struct Proved {
    /// A name of a module `def` or `class`, or an attribute chain on it: the name of its root.
    local: HashMap<TextRange, String>,
    /// A `sys.path` that a read uses.
    path: HashSet<TextRange>,
}

/// The proof facts of each module. `fixed` lists the names that a module `def` never makes local:
/// the builtin doors and the import functions.
pub(super) fn proved(modules: &[Item], fixed: &[&[&str]]) -> Vec<Proved> {
    let each = |(tree, unique, imports): &Item| Proved::of(tree, (imports, unique), fixed);
    modules.iter().map(each).collect()
}

impl Proved {
    fn of(
        tree: &ModModule,
        (imports, unique): (&Bindings, &HashSet<String>),
        fixed: &[&[&str]],
    ) -> Self {
        let defined = tree.body.iter().filter_map(|stmt| match stmt {
            Stmt::FunctionDef(node) => Some(node.name.as_str()),
            Stmt::ClassDef(node) => Some(node.name.as_str()),
            _ => None,
        });
        let local = defined
            .filter(|name| unique.contains(*name) && !imports.contains_key(*name))
            .filter(|name| !fixed.iter().any(|names| names.contains(name)))
            .map(str::to_owned)
            .collect();
        let mut sys = HashSet::new();
        for (name, origins) in imports.iter().filter(|(name, _)| unique.contains(*name)) {
            if origins.as_slice() == ["sys"] {
                sys.insert(name.clone());
            }
        }
        let mut marks = Marks {
            local,
            sys,
            found: Self {
                local: HashMap::new(),
                path: HashSet::new(),
            },
        };
        marks.visit_body(&tree.body);
        marks.found
    }

    /// True when the site is no door. `kind` tells whether the site is a dynamic import or an
    /// import-system change; a site of another kind is never covered.
    pub(super) fn covers(&self, kind: (bool, bool), detail: &str, range: TextRange) -> bool {
        let (dynamic, system) = kind;
        let under = |root: &String| {
            detail == root
                || detail
                    .strip_prefix(root.as_str())
                    .is_some_and(|rest| rest.starts_with('.'))
        };
        let door = self.local.get(&range).is_some_and(under);
        (dynamic && door) || (system && detail == "sys.path" && self.path.contains(&range))
    }
}

/// The walk that finds the sites of `Proved`.
struct Marks {
    local: HashSet<String>,
    sys: HashSet<String>,
    found: Proved,
}

impl Marks {
    /// `sys.path` as a plain attribute of a name for `sys`, in a position that only reads.
    fn read(&mut self, expr: &Expr) {
        if let Expr::Attribute(node) = expr {
            let sys =
                matches!(&*node.value, Expr::Name(name) if self.sys.contains(name.id.as_str()));
            if sys && node.attr.as_str() == "path" && node.ctx == ExprContext::Load {
                self.found.path.insert(node.range());
            }
        }
    }

    /// The root name of an attribute chain decides the kind of the chain.
    fn chain(&mut self, expr: &Expr) {
        let mut base = expr;
        while let Expr::Attribute(node) = base {
            base = &node.value;
        }
        let Expr::Name(root) = base else { return };
        let id = root.id.as_str();
        if self.local.contains(id) {
            self.found.local.insert(expr.range(), id.to_owned());
        }
    }
}

impl<'a> Visitor<'a> for Marks {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        if let Stmt::For(node) = stmt {
            self.read(&node.iter);
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_comprehension(&mut self, comprehension: &'a Comprehension) {
        self.read(&comprehension.iter);
        visitor::walk_comprehension(self, comprehension);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Name(node) if self.local.contains(node.id.as_str()) => {
                self.found.local.insert(node.range(), node.id.to_string());
            }
            Expr::Attribute(_) => self.chain(expr),
            Expr::Subscript(node) if node.ctx == ExprContext::Load => self.read(&node.value),
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

/// A module name, its tree, its unique names and whether it can directly export a class.
pub(in crate::survey) type ClassItem<'a> = (&'a str, &'a ModModule, HashSet<String>, bool);

/// True when each site reads a proven class literal, and no reflective helper can write it.
pub(in crate::survey) fn only_class_data_reads<'a>(
    candidates: impl Iterator<Item = Option<(usize, TextRange)>>,
    modules: impl Iterator<Item = ClassItem<'a>>,
    outside: &HashSet<String>,
    stable: impl Fn(&str) -> bool + Copy,
) -> bool {
    let Some(sites) = candidates.collect::<Option<Vec<_>>>() else {
        return false;
    };
    if sites.is_empty() || !["code", "__class__", "__bases__"].into_iter().all(stable) {
        return false;
    }
    let modules: Vec<_> = modules.collect();
    class_data_reads(&modules, outside, stable).is_some_and(|reads| {
        sites
            .into_iter()
            .all(|(index, range)| reads.get(index).is_some_and(|found| found.contains(&range)))
    })
}

fn class_data_reads(
    modules: &[ClassItem<'_>],
    outside: &HashSet<String>,
    stable: impl Fn(&str) -> bool + Copy,
) -> Option<Vec<HashSet<TextRange>>> {
    let names = modules.iter().filter(|(name, _, _, exports)| {
        *exports
            && !outside.contains(*name)
            && str::split(name, '.').all(stable)
            && !outside.iter().any(|parent| {
                str::strip_prefix(name, parent).is_some_and(|rest| rest.starts_with('.'))
            })
    });
    let classes: HashMap<_, _> = names
        .map(|(module, tree, unique, _)| {
            let names = tree.body.iter().filter_map(literal_code_class);
            let proven: HashSet<_> = names
                .filter(|name| stable(name) && unique.contains(*name))
                .collect();
            (*module, proven)
        })
        .collect();
    modules
        .iter()
        .map(|(module, tree, unique, _)| {
            let mut marks = ClassReads {
                names: literal_code_imports(tree, unique, &classes, stable),
                found: HashSet::new(),
                reflective: false,
            };
            marks.visit_body(&tree.body);
            if outside.contains(*module) {
                marks.found.clear();
            }
            (!marks.reflective).then_some(marks.found)
        })
        .collect()
}

/// No bases, decorator or class-body code can replace the literal or customize its lookup.
fn literal_code_class(stmt: &Stmt) -> Option<&str> {
    let Stmt::ClassDef(class) = stmt else {
        return None;
    };
    if !<[_]>::is_empty(&class.decorator_list)
        || class.arguments.is_some()
        || class.type_params.is_some()
    {
        return None;
    }
    let mut code = false;
    for statement in &class.body {
        match statement {
            Stmt::Pass(_) => {}
            Stmt::Expr(node) if matches!(&*node.value, Expr::StringLiteral(_)) => {}
            Stmt::Assign(node) if scalar_literal(&node.value) => {
                let [Expr::Name(name)] = node.targets.as_slice() else {
                    return None;
                };
                if Name::as_str(&name.id).starts_with("__") {
                    return None;
                }
                code |= Name::as_str(&name.id) == "code";
            }
            _ => return None,
        }
    }
    code.then(|| Identifier::as_str(&class.name))
}

fn literal_code_imports<'a>(
    tree: &'a ModModule,
    unique: &HashSet<String>,
    classes: &HashMap<&str, HashSet<&str>>,
    stable: impl Fn(&str) -> bool,
) -> HashSet<&'a str> {
    let mut found = HashSet::new();
    for stmt in &tree.body {
        let Stmt::ImportFrom(import) = stmt else {
            continue;
        };
        let Some(module) = import.module.as_ref().filter(|_| import.level == 0) else {
            continue;
        };
        let Some(eligible) = classes.get(Identifier::as_str(module)) else {
            continue;
        };
        for alias in &import.names {
            let local = Identifier::as_str(alias.asname.as_ref().unwrap_or(&alias.name));
            if eligible.contains(Identifier::as_str(&alias.name))
                && stable(local)
                && unique.contains(local)
            {
                found.insert(local);
            }
        }
    }
    found
}

struct ClassReads<'a> {
    names: HashSet<&'a str>,
    found: HashSet<TextRange>,
    reflective: bool,
}

impl<'a> Visitor<'a> for ClassReads<'_> {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        self.reflective |= matches!(stmt, Stmt::ImportFrom(import)
            if import.names.iter().any(|alias| reflective_writer(Identifier::as_str(&alias.name))));
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        self.reflective |= match expr {
            Expr::Name(node) => reflective_writer(Name::as_str(&node.id)),
            Expr::Attribute(node) => {
                reflective_writer(Identifier::as_str(&node.attr))
                    || matches!(Identifier::as_str(&node.attr), "setattr" | "delattr")
            }
            _ => false,
        };
        if let Expr::Attribute(node) = expr {
            if node.ctx == ExprContext::Load
                && Identifier::as_str(&node.attr) == "code"
                && matches!(&*node.value, Expr::Name(name) if self.names.contains(Name::as_str(&name.id)))
            {
                self.found.insert(node.range());
            }
        }
        visitor::walk_expr(self, expr);
    }
}

// An attribute helper can return a bound writer (for example, type.__setattr__).
fn reflective_writer(name: &str) -> bool {
    matches!(name, "getattr" | "__getattribute__" | "attrgetter")
}
