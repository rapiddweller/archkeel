// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names of the standard library that a whole outside file uses only to read (D9, #1963,
//! AD-1146): `importlib` calls that give text, a path or a bare answer, and tests of
//! `sys.modules`. The use of a result decides, not the call: a `files(...)` path that is written
//! rewrites a file of the scan. Any other use, an alias or a `from` import ends the proof.

use std::collections::{HashMap, HashSet};

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    CmpOp, Comprehension, ExceptHandler, Expr, ExprCall, ExprCompare, ExprContext, ExprName,
    Identifier, Operator, Parameter, Pattern, Stmt, StmtAssign, StmtImport, StmtImportFrom,
};
use ruff_text_size::{Ranged, TextRange};

use crate::module::Module;

/// The names of the standard library that the whole file uses only to read (D9, #1963).
#[derive(Clone, Copy, Default)]
pub(super) struct Reads {
    /// Each use of `importlib` is a call that gives text, a path or a bare answer: `metadata`
    /// `version`, `resources` `files`, `util` `find_spec` tested against `None`.
    pub importlib: bool,
    /// Each use of `sys.modules` tests a name or walks the names: no module object leaves it.
    pub sys_modules: bool,
}

/// The attribute chains of `importlib` that give no module object and write no binding.
const IMPORTLIB_READS: [&str; 4] = [
    "importlib.metadata.version",
    "importlib.metadata.PackageNotFoundError",
    "importlib.resources.files",
    "importlib.util.find_spec",
];

/// The attributes of `sys` that hand out no namespace of modules. Any other attribute (`__dict__`
/// holds `modules`) ends the proof for `sys.modules`.
const SYS_READS: [&str; 12] = [
    "sys.argv",
    "sys.base_prefix",
    "sys.executable",
    "sys.exit",
    "sys.flags",
    "sys.flags.isolated",
    "sys.path",
    "sys.platform",
    "sys.prefix",
    "sys.stderr",
    "sys.stdout",
    "sys.version_info",
];

/// The calls on a `files(...)` path that give text, bytes or a bare answer. Any other call (a
/// write, an `open`, `iterdir`) can change the file of a module of the scan.
const PATH_READS: [&str; 5] = ["read_text", "read_bytes", "is_file", "is_dir", "exists"];

const FILES: &str = "importlib.resources.files";

#[derive(Default)]
struct Uses {
    safe: HashSet<TextRange>,
    importlib: bool,
    sys_modules: bool,
    /// The names that bind a `files(...)` result, with the range of each such call.
    bound: HashMap<String, Vec<TextRange>>,
    /// The ranges of the calls that a name binds: `judge` leaves them to the check of the name.
    pending: HashSet<TextRange>,
    /// Each load and each store of a name, and the names that a path read starts from.
    loads: Vec<(String, TextRange)>,
    stores: HashMap<String, usize>,
    receivers: HashSet<TextRange>,
}
impl Uses {
    fn mark(&mut self, expr: &Expr) {
        self.safe.insert(expr.range());
    }
    fn iterate(&mut self, generators: &[Comprehension]) {
        for generator in generators {
            self.mark(&generator.iter);
        }
    }
}
/// The dotted name of a chain of attributes on a name, or `None` for any other expression.
fn chain(expr: &Expr) -> Option<String> {
    match expr {
        Expr::Name(name) => Some(name.id.to_string()),
        Expr::Attribute(node) => Some(format!(
            "{}.{}",
            chain(&node.value)?,
            Identifier::as_str(&node.attr)
        )),
        _ => None,
    }
}

impl Uses {
    /// A test of a name (`in`) reads no object of `sys.modules`; `find_spec(...) is None` reads no
    /// module.
    fn compare(&mut self, node: &ExprCompare) {
        let ops = node.ops.iter();
        if ops.clone().all(|op| matches!(op, CmpOp::In | CmpOp::NotIn)) {
            // Only the last operand: an inner operand is also the left side of the next test, and
            // its `__contains__` would get the dictionary (`x in sys.modules in sink`).
            node.operands
                .last()
                .into_iter()
                .for_each(|side| self.mark(side));
        }
        let none = node.operands.iter().skip(1).all(Expr::is_none_literal_expr);
        if !(none && ops.clone().all(|op| matches!(op, CmpOp::Is | CmpOp::IsNot))) {
            return;
        }
        if let Some(Expr::Call(call)) = node.operands.first() {
            self.mark(&call.func);
        }
    }

    /// The `files(...)` result of a path read. `files(..) / "x"` and `.joinpath(..)` keep a path;
    /// the read call ends it. The use of the result decides, not the call of `files`.
    fn receiver(&mut self, mut expr: &Expr) {
        loop {
            match expr {
                Expr::BinOp(node) if matches!(node.op, Operator::Div) => expr = &node.left,
                Expr::Call(call) => match &*call.func {
                    Expr::Attribute(node) if Identifier::as_str(&node.attr) == "joinpath" => {
                        expr = &node.value;
                    }
                    func if chain(func).as_deref() == Some(FILES) => {
                        return self.mark(func);
                    }
                    _ => return,
                },
                Expr::Name(name) => {
                    self.receivers.insert(name.range);
                    return;
                }
                _ => return,
            }
        }
    }

    /// The call `x.read_text()` on a path: `x` starts a read.
    fn path_read(&mut self, call: &ExprCall) {
        if let Expr::Attribute(node) = &*call.func {
            if PATH_READS.contains(&Identifier::as_str(&node.attr)) {
                self.receiver(&node.value);
            }
        }
    }

    /// `name = files(...)` binds a path; a store counts for each name.
    fn assign(&mut self, node: &StmtAssign) {
        if let ([Expr::Name(target)], Expr::Call(call)) = (&node.targets[..], &*node.value) {
            if chain(&call.func).as_deref() == Some(FILES) {
                let id = target.id.to_string();
                self.bound.entry(id).or_default().push(call.func.range());
                self.pending.insert(call.func.range());
            }
        }
    }

    /// Count a name; `true` when it is `importlib` or `sys` and was judged.
    fn name(&mut self, node: &ExprName, expr: &Expr) -> bool {
        let id = node.id.to_string();
        if matches!(node.ctx, ExprContext::Load) {
            self.loads.push((id, node.range));
            return self.judge(expr);
        }
        self.rebound(&id);
        *self.stores.entry(id).or_default() += 1;
        false
    }

    /// `import importlib.x as y` hides the chain; `import z as sys` binds another object.
    fn import(&mut self, node: &StmtImport) {
        for alias in &node.names {
            let name = Identifier::as_str(&alias.name);
            let aliased = alias.asname.is_some();
            self.importlib |= aliased && name.starts_with("importlib");
            self.sys_modules |= aliased && name == "sys";
            if let Some(asname) = &alias.asname {
                self.rebound(Identifier::as_str(asname));
            }
        }
    }

    /// `from importlib import x` hides the chain; `from z import sys` binds another object.
    fn import_from(&mut self, node: &StmtImportFrom) {
        let from = node.module.as_ref().map_or("", Identifier::as_str);
        self.importlib |= from.starts_with("importlib");
        self.sys_modules |= from == "sys";
        for alias in &node.names {
            let bound = alias.asname.as_ref().unwrap_or(&alias.name);
            self.rebound(Identifier::as_str(bound));
        }
    }

    /// A name that stands for `sys` or `importlib` is bound to something else: the proof for
    /// that name ends, because the object can run any code at a test (`x in sys.modules`).
    fn rebound(&mut self, id: &str) {
        self.sys_modules |= id == "sys";
        self.importlib |= id == "importlib";
    }

    /// A name that binds a `files(...)` result is read only when it is stored once and each load
    /// is the start of a path read.
    fn names_bound(&self) -> bool {
        self.bound.iter().all(|(name, calls)| {
            let once = self.stores.get(name) == Some(&1) && Vec::len(calls) == 1;
            let loads = self.loads.iter().filter(|(found, _)| found == name);
            once && loads
                .into_iter()
                .all(|(_, range)| self.receivers.contains(range))
        })
    }

    /// Judge a chain rooted at `importlib` or `sys`. `false` for any other chain.
    fn judge(&mut self, expr: &Expr) -> bool {
        let Some(text) = chain(expr) else {
            return false;
        };
        let safe = self.safe.contains(&expr.range());
        match text.split('.').next() {
            Some("importlib") => {
                let proved = safe || self.pending.contains(&expr.range());
                let guarded = text == "importlib.util.find_spec" || text == FILES;
                self.importlib |=
                    !(IMPORTLIB_READS.contains(&String::as_str(&text)) && (!guarded || proved));
            }
            Some("sys") if text == "sys.modules" => self.sys_modules |= !safe,
            Some("sys") => self.sys_modules |= !SYS_READS.contains(&String::as_str(&text)),
            _ => return false,
        }
        true
    }
}

impl<'a> Visitor<'a> for Uses {
    fn visit_stmt(&mut self, stmt: &'a Stmt) {
        match stmt {
            Stmt::Import(node) => self.import(node),
            Stmt::ImportFrom(node) => self.import_from(node),
            Stmt::FunctionDef(node) => self.rebound(Identifier::as_str(&node.name)),
            Stmt::ClassDef(node) => self.rebound(Identifier::as_str(&node.name)),
            Stmt::For(node) => self.mark(&node.iter),
            Stmt::Assign(node) => self.assign(node),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_parameter(&mut self, parameter: &'a Parameter) {
        self.rebound(Identifier::as_str(&parameter.name));
        visitor::walk_parameter(self, parameter);
    }

    fn visit_except_handler(&mut self, handler: &'a ExceptHandler) {
        let ExceptHandler::ExceptHandler(node) = handler;
        if let Some(name) = &node.name {
            self.rebound(Identifier::as_str(name));
        }
        visitor::walk_except_handler(self, handler);
    }

    fn visit_pattern(&mut self, pattern: &'a Pattern) {
        match pattern {
            Pattern::MatchAs(node) => {
                if let Some(name) = &node.name {
                    self.rebound(Identifier::as_str(name));
                }
            }
            Pattern::MatchStar(node) => {
                if let Some(name) = &node.name {
                    self.rebound(Identifier::as_str(name));
                }
            }
            _ => {}
        }
        visitor::walk_pattern(self, pattern);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Compare(node) => self.compare(node),
            Expr::ListComp(node) => self.iterate(&node.generators),
            Expr::SetComp(node) => self.iterate(&node.generators),
            Expr::DictComp(node) => self.iterate(&node.generators),
            Expr::Generator(node) => self.iterate(&node.generators),
            Expr::Call(node) => self.path_read(node),
            Expr::Name(node) if self.name(node, expr) => return,
            Expr::Attribute(_) if self.judge(expr) => return,
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

/// What the file reads with `importlib` and `sys.modules`. A write, a subscript, an alias, a
/// `from` import or a value that is passed on ends the proof for that name.
pub(super) fn of(module: &Module) -> Reads {
    let mut uses = Uses::default();
    uses.visit_body(&module.tree.body);
    Reads {
        importlib: !uses.importlib && uses.names_bound(),
        sys_modules: !uses.sys_modules,
    }
}
