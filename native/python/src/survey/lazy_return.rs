// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The value that the lazy `__getattr__` returns for each key of its table (AD-654).
//!
//! AD-560 bounds the import calls of the function, not the value that it returns. This proof runs
//! the body once for each key, with the requested name set to the key, and once for a name that
//! is no key. A test that the strings decide picks its branch; any other test runs both branches,
//! and a name that the branches bind to two values is unknown after them. A loop over the table
//! runs once per entry. A key is proven when each `return` that its run reaches gives the same
//! value: `getattr(import_module(target), literal)` or `import_module(target)`. A run that ends
//! without `return` gives `None` and proves nothing.
//!
//! Each `globals()` store of any run must write a key of the table with the proven value of that
//! key, else the key is not proven. Any other form fails the whole proof: a statement that this
//! walk does not read (`try`, `while`, `with`, `del`, `break`), a walrus, a store into anything but
//! `globals()`, a `globals()` value that leaves a subscript store, a store key that is no key of the
//! table, or a key that names a global that the function reads.

use std::collections::{BTreeMap, HashMap, HashSet};

use ruff_python_ast::visitor::Visitor;
use ruff_python_ast::{BoolOp, Expr, ExprCall, ExprContext, Stmt, StmtFunctionDef, UnaryOp};

use super::lazy_binds::Binds;
use super::lazy_cover::Source;
use super::lazy_flow::Callee;
use super::lazy_shape::{closed, global_reads, jumps, plain_parameter};
use super::lazy_table::Table;
use super::lazy_value::{compare, join, text, Env, Val};

/// What the proof reads beside the function and the table.
pub(super) struct Context<'a> {
    pub callee: Callee,
    /// True when the module never binds the name, so it is the builtin.
    pub free: &'a dyn Fn(&str) -> bool,
    /// The module that `import_module(name, package)` names, if it is a module name.
    pub resolve: &'a dyn Fn(&str, Option<&str>) -> Option<String>,
}

/// The values of the elements of a tuple target: the parts of an entry or a pair of the same
/// length, else unknown for each element.
fn unpack(value: Val, elements: &[Expr]) -> Vec<Val> {
    let parts: Option<Vec<Val>> = match value {
        Val::Entry(items) => Some(items.into_iter().map(Val::Str).collect()),
        Val::Pair(key, items) => Some(vec![Val::Str(key), Val::Entry(items)]),
        _ => None,
    };
    let starred = elements.iter().any(Expr::is_starred_expr);
    parts
        .filter(|parts| parts.len() == elements.len() && !starred)
        .unwrap_or_else(|| vec![Val::Unknown; elements.len()])
}

#[cfg(test)]
#[path = "lazy_return_tests.rs"]
mod tests;

/// The proven value of each key of the table.
pub(super) fn sources(
    function: &StmtFunctionDef,
    table: &Table,
    cx: &Context,
) -> BTreeMap<String, Source> {
    let none = BTreeMap::new();
    let Some(param) = plain_parameter(function)
        .filter(|one| one.default.is_none())
        .map(|one| one.parameter.name.as_str())
    else {
        return none;
    };
    let mut binds = Binds::new(&table.name);
    binds.visit_body(&function.body);
    if binds.bad || !closed(function, &binds.map) {
        return none;
    }
    let mut locals: HashSet<String> = binds.map.into_keys().collect();
    locals.insert(param.to_owned());
    let entries: Vec<(String, Vec<String>)> = dedup(&table.entries);
    let lookup: HashMap<&str, &Vec<String>> = entries
        .iter()
        .map(|(key, items)| (key.as_str(), items))
        .collect();
    let run = Run {
        cx,
        table,
        locals: &locals,
        entries: &entries,
        lookup: &lookup,
    };
    let mut found = BTreeMap::new();
    let mut writes = Vec::new();
    let names: Vec<Val> = table
        .keys
        .iter()
        .map(|key| Val::Str(key.clone()))
        .chain([Val::NonKey])
        .collect();
    for name in names {
        let mut state = State::default();
        let env = Env::from([(param.to_owned(), name.clone())]);
        if run.body(&function.body, Some(env), &mut state).is_some() {
            state.returns.push(Val::NoneValue);
        }
        if state.fatal {
            return none;
        }
        writes.extend(state.writes);
        let (Val::Str(key), [first, rest @ ..]) = (name, state.returns.as_slice()) else {
            continue;
        };
        if let (Val::Value(source), true) = (first, rest.iter().all(|item| item == first)) {
            found.insert(key, source.clone());
        }
    }
    let read = global_reads(function, &locals);
    for (key, value) in writes {
        let Val::Str(key) = key else {
            return none;
        };
        if !table.keys.contains(&key) || read.contains(&key) || key == table.name {
            return none;
        }
        if found.get(&key).map(|source| Val::Value(source.clone())) != Some(value) {
            found.remove(&key);
        }
    }
    found
}

/// The table entries as the dict holds them: a key once, at its first place, with its last value.
fn dedup(entries: &[(String, Vec<String>)]) -> Vec<(String, Vec<String>)> {
    let mut out: Vec<(String, Vec<String>)> = Vec::new();
    for (key, items) in entries {
        match out.iter_mut().find(|item| &item.0 == key) {
            Some(item) => item.1.clone_from(items),
            None => out.push((key.clone(), items.clone())),
        }
    }
    out
}

/// The run of the body for one requested name, and what it found.
#[derive(Default)]
struct State {
    returns: Vec<Val>,
    writes: Vec<(Val, Val)>,
    fatal: bool,
}

struct Run<'a> {
    cx: &'a Context<'a>,
    table: &'a Table,
    locals: &'a HashSet<String>,
    entries: &'a [(String, Vec<String>)],
    lookup: &'a HashMap<&'a str, &'a Vec<String>>,
}

impl Run<'_> {
    /// The environment after the statements, or `None` when no path leaves them.
    fn body(&self, body: &[Stmt], mut env: Option<Env>, state: &mut State) -> Option<Env> {
        for stmt in body {
            let current = env?;
            env = self.stmt(stmt, current, state);
            if state.fatal {
                return None;
            }
        }
        env
    }

    fn stmt(&self, stmt: &Stmt, mut env: Env, state: &mut State) -> Option<Env> {
        match stmt {
            Stmt::Expr(_) | Stmt::Pass(_) | Stmt::Assert(_) => Some(env),
            Stmt::Return(node) => {
                let value = node
                    .value
                    .as_ref()
                    .map_or(Val::NoneValue, |expr| self.eval(expr, &env));
                state.returns.push(value);
                None
            }
            Stmt::Raise(_) => None,
            Stmt::Import(_) | Stmt::ImportFrom(_) => {
                for name in super::binders::import_bindings(stmt) {
                    env.insert(name, Val::Unknown);
                }
                Some(env)
            }
            Stmt::Assign(node) => match node.targets.as_slice() {
                [target] => {
                    let value = self.eval(&node.value, &env);
                    self.assign(target, value, &mut env, state);
                    Some(env)
                }
                _ => self.fail(state),
            },
            Stmt::AnnAssign(node) => match (&*node.target, &node.value) {
                (Expr::Name(_), Some(value)) => {
                    let value = self.eval(value, &env);
                    self.assign(&node.target, value, &mut env, state);
                    Some(env)
                }
                _ => self.fail(state),
            },
            Stmt::AugAssign(node) => match &*node.target {
                Expr::Name(name) => {
                    env.insert(name.id.to_string(), Val::Unknown);
                    Some(env)
                }
                _ => self.fail(state),
            },
            Stmt::If(node) => {
                let mut clauses = vec![(Some(&*node.test), node.body.as_slice())];
                let more = node.elif_else_clauses.iter();
                clauses.extend(more.map(|clause| (clause.test.as_ref(), clause.body.as_slice())));
                self.branches(&clauses, env, state)
            }
            Stmt::For(node) => self.each(node, env, state),
            _ => self.fail(state),
        }
    }

    fn fail(&self, state: &mut State) -> Option<Env> {
        state.fatal = true;
        None
    }

    /// The clauses of one `if`: a decided test picks its body, an open test runs both ways.
    fn branches(
        &self,
        clauses: &[(Option<&Expr>, &[Stmt])],
        env: Env,
        state: &mut State,
    ) -> Option<Env> {
        let mut ends = Vec::new();
        for (test, body) in clauses {
            match test.map_or(Some(true), |test| self.test(test, &env)) {
                Some(true) => {
                    ends.push(self.body(body, Some(env), state));
                    return join(ends);
                }
                Some(false) => {}
                None => ends.push(self.body(body, Some(env.clone()), state)),
            }
        }
        ends.push(Some(env));
        join(ends)
    }

    /// A `for` loop over `table.items()`, `table.keys()` or `table.values()`: one run per entry.
    fn each(&self, node: &ruff_python_ast::StmtFor, env: Env, state: &mut State) -> Option<Env> {
        let Expr::Call(call) = &*node.iter else {
            return self.fail(state);
        };
        let method = match &*call.func {
            Expr::Attribute(attr)
                if self.eval(&attr.value, &env) == Val::Table
                    && call.arguments.args.is_empty()
                    && call.arguments.keywords.is_empty() =>
            {
                attr.attr.as_str()
            }
            _ => return self.fail(state),
        };
        if node.is_async || jumps(&node.body) {
            return self.fail(state);
        }
        let mut env = Some(env);
        for (key, items) in self.entries {
            let value = match method {
                "items" => Val::Pair(key.clone(), items.clone()),
                "keys" => Val::Str(key.clone()),
                "values" => Val::Entry(items.clone()),
                _ => return self.fail(state),
            };
            let mut current = env?;
            self.assign(&node.target, value, &mut current, state);
            env = self.body(&node.body, Some(current), state);
        }
        self.body(&node.orelse, env, state)
    }

    /// Bind a target: a name, a tuple that unpacks an entry or a pair, or a `globals()` store.
    fn assign(&self, target: &Expr, value: Val, env: &mut Env, state: &mut State) {
        match target {
            Expr::Name(name) => {
                env.insert(name.id.to_string(), value);
            }
            Expr::Tuple(tuple) => {
                for (element, part) in tuple.elts.iter().zip(unpack(value, &tuple.elts)) {
                    self.assign(element, part, env, state);
                }
            }
            Expr::Subscript(node) if self.eval(&node.value, env) == Val::Globals => {
                state.writes.push((self.eval(&node.slice, env), value));
            }
            _ => state.fatal = true,
        }
    }

    /// The value of an expression.
    fn eval(&self, expr: &Expr, env: &Env) -> Val {
        match expr {
            Expr::Name(node) => {
                let name = node.id.as_str();
                if self.locals.contains(name) {
                    env.get(name).cloned().unwrap_or(Val::Unknown)
                } else if name == self.table.name {
                    Val::Table
                } else {
                    Val::Unknown
                }
            }
            Expr::NoneLiteral(_) => Val::NoneValue,
            Expr::Call(call) => self.call(call, env),
            Expr::Subscript(node) if node.ctx == ExprContext::Load => {
                match (self.eval(&node.value, env), self.eval(&node.slice, env)) {
                    (Val::Table, Val::Str(key)) => self.entry(&key),
                    (Val::Entry(items), Val::Index(at)) => {
                        items.get(at).cloned().map_or(Val::Unknown, Val::Str)
                    }
                    _ => Val::Unknown,
                }
            }
            Expr::NumberLiteral(node) => node
                .value
                .as_int()
                .and_then(ruff_python_ast::Int::as_usize)
                .map_or(Val::Unknown, Val::Index),
            _ => text(expr, &|item| self.eval(item, env)).map_or(Val::Unknown, Val::Str),
        }
    }

    fn entry(&self, key: &str) -> Val {
        self.lookup
            .get(key)
            .map_or(Val::Unknown, |items| Val::Entry((*items).clone()))
    }

    /// True when the name is the builtin of that name in the function.
    fn builtin(&self, func: &Expr, name: &str) -> bool {
        matches!(func, Expr::Name(node) if node.id.as_str() == name)
            && !self.locals.contains(name)
            && (self.cx.free)(name)
    }

    fn call(&self, call: &ExprCall, env: &Env) -> Val {
        let arguments = &call.arguments;
        let args: Vec<Val> = arguments
            .args
            .iter()
            .map(|arg| self.eval(arg, env))
            .collect();
        let plain = arguments.keywords.is_empty();
        if let Expr::Attribute(node) = &*call.func {
            if node.attr.as_str() == "get" && self.eval(&node.value, env) == Val::Table && plain {
                return match args.as_slice() {
                    [Val::Str(key)] => match self.lookup.get(key.as_str()) {
                        Some(items) => Val::Entry((*items).clone()),
                        None => Val::NoneValue,
                    },
                    [Val::NonKey] => Val::NoneValue,
                    _ => Val::Unknown,
                };
            }
        }
        if self.builtin(&call.func, "globals") && args.is_empty() && plain {
            return Val::Globals;
        }
        if self.builtin(&call.func, "getattr") && plain {
            if let [Val::Value(Source::Module(target)), Val::Str(name)] = args.as_slice() {
                return Val::Value(Source::Attr(target.clone(), name.clone()));
            }
            return Val::Unknown;
        }
        if self.import_call(&call.func) {
            return self.import(&args, call, env);
        }
        Val::Unknown
    }

    /// `import_module(name)`, `import_module(name, package)` or with `package=`: the module.
    fn import(&self, args: &[Val], call: &ExprCall, env: &Env) -> Val {
        let package = match (args, call.arguments.keywords.as_ref()) {
            ([_], []) => Val::NoneValue,
            ([_, package], []) => package.clone(),
            ([_], [keyword]) if keyword.arg.as_ref().is_some_and(|arg| arg == "package") => {
                self.eval(&keyword.value, env)
            }
            _ => return Val::Unknown,
        };
        let package = match package {
            Val::NoneValue => None,
            Val::Str(package) => Some(package),
            _ => return Val::Unknown,
        };
        let Some(Val::Str(name)) = args.first() else {
            return Val::Unknown;
        };
        (self.cx.resolve)(name, package.as_deref())
            .map_or(Val::Unknown, |target| Val::Value(Source::Module(target)))
    }

    /// True when the callee is the proven `import_module` (`lazy.rs`).
    fn import_call(&self, func: &Expr) -> bool {
        match func {
            Expr::Name(node) => {
                node.id.as_str() == "import_module"
                    && !self.locals.contains("import_module")
                    && self.cx.callee.from_import
            }
            Expr::Attribute(node) => {
                node.attr.as_str() == "import_module"
                    && matches!(&*node.value, Expr::Name(base)
                        if base.id.as_str() == "importlib" && !self.locals.contains("importlib"))
                    && self.cx.callee.plain
            }
            _ => false,
        }
    }

    /// The truth of a test, when the strings decide it.
    fn test(&self, test: &Expr, env: &Env) -> Option<bool> {
        match test {
            Expr::BoolOp(node) => {
                let values: Vec<Option<bool>> = node
                    .values
                    .iter()
                    .map(|value| self.test(value, env))
                    .collect();
                let deciding = node.op == BoolOp::Or;
                if values.contains(&Some(deciding)) {
                    Some(deciding)
                } else {
                    values.iter().all(Option::is_some).then_some(!deciding)
                }
            }
            Expr::UnaryOp(node) if node.op == UnaryOp::Not => {
                self.test(&node.operand, env).map(|value| !value)
            }
            Expr::Compare(node) => {
                let ([left, right], [op]) = (&*node.operands, &*node.ops) else {
                    return None;
                };
                let (left, right) = (self.eval(left, env), self.eval(right, env));
                compare(*op, &left, &right, &self.table.keys)
            }
            _ => None,
        }
    }
}
