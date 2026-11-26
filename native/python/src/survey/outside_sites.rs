// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The hazard sites of a Python file of the repository outside the scan (#1522, AD-770).
//!
//! A trojan horse can give the object of a module of the scan by its name. The file then spells the name
//! in a string, so each module that a string of the file names escapes (`named`). A name that the
//! file does not spell comes from data or from other code: the stated premise of the run covers it.
//!
//! Three forms give no module of the scan (`harmless`):
//! - `import_module(name)` or `__import__(name)` where each value that `name` can have is a text,
//!   or starts with a text, that is not a module of the scan, no package above one, and no prefix
//!   of one: `f"fixtures.demo_{x}"`, `"a" if c else "b"`. A name that starts with `.` is relative,
//!   so it is no such text.
//! - `exec`, `eval` or `compile` of a literal text whose code has no name, no attribute, no call
//!   and no subscript: `eval("1 + 1")`, `exec("pass")`.
//! - `spec_from_file_location("<text>", path)` where the text is a literal that names no module of
//!   the scan, no package above one and no prefix of one. The call and the loader calls that use its
//!   spec (`module_from_spec`, `exec_module`, the `importlib.util` import) make a new module object
//!   under a foreign name. That object is no module of the scan. Its code is read by the walk, or
//!   it is a test source or outside the repository (the stated premise). The rule holds only for a
//!   file in which each `spec_from_file_location` call has such a name (AD-1049).

use std::collections::HashSet;

use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{
    CmpOp, Comprehension, Expr, ExprCall, ExprCompare, FStringPartRef, Identifier,
    InterpolatedStringElement, InterpolatedStringElements, Keyword, Operator, Stmt,
};
use ruff_text_size::{Ranged, TextRange};

use super::super::hazards::Site;
use super::native::reached;
use crate::module::Module;
use crate::parse::parse;

/// The loader calls of a file whose spec names are all foreign (AD-1049).
const LOADER_CALLS: [&str; 2] = ["module_from_spec", "exec_module"];

/// The import statements of the `importlib.util` loader names.
const LOADER_IMPORTS: [&str; 4] = [
    "importlib",
    "importlib.util",
    "importlib.util.spec_from_file_location",
    "importlib.util.module_from_spec",
];

/// The sites of one file, with the fact that decides the loader calls (`foreign_specs`).
pub(super) struct File<'a> {
    pub module: &'a Module,
    pub foreign_specs: bool,
    pub reads: Reads,
}

/// The names of the standard library that the whole file uses only to read (D9, #1963).
#[derive(Clone, Copy, Default)]
pub(super) struct Reads {
    /// Each use of `importlib` is a call that gives text, a path or a bare answer: `metadata`
    /// `version`, `resources` `files`, `util` `find_spec` tested against `None`.
    importlib: bool,
    /// Each use of `sys.modules` tests a name or walks the names: no module object leaves it.
    sys_modules: bool,
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
const SYS_READS: [&str; 6] = [
    "sys.argv",
    "sys.executable",
    "sys.exit",
    "sys.platform",
    "sys.stderr",
    "sys.stdout",
];

#[derive(Default)]
struct Uses {
    safe: HashSet<TextRange>,
    importlib: bool,
    sys_modules: bool,
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
            node.operands
                .iter()
                .skip(1)
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

    /// Judge a chain rooted at `importlib` or `sys`. `false` for any other chain.
    fn judge(&mut self, expr: &Expr) -> bool {
        let Some(text) = chain(expr) else {
            return false;
        };
        let safe = self.safe.contains(&expr.range());
        match text.split('.').next() {
            Some("importlib") => {
                let spec = text == "importlib.util.find_spec";
                self.importlib |=
                    !(IMPORTLIB_READS.contains(&String::as_str(&text)) && (!spec || safe));
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
            Stmt::Import(node) => {
                for alias in &node.names {
                    let name = Identifier::as_str(&alias.name);
                    let aliased = alias.asname.is_some();
                    self.importlib |= aliased && name.starts_with("importlib");
                    self.sys_modules |= aliased && name == "sys";
                }
            }
            Stmt::ImportFrom(node) => {
                let from = node.module.as_ref().map_or("", Identifier::as_str);
                self.importlib |= from.starts_with("importlib");
                self.sys_modules |= from == "sys";
            }
            Stmt::For(node) => self.mark(&node.iter),
            _ => {}
        }
        visitor::walk_stmt(self, stmt);
    }

    fn visit_expr(&mut self, expr: &'a Expr) {
        match expr {
            Expr::Compare(node) => self.compare(node),
            Expr::ListComp(node) => self.iterate(&node.generators),
            Expr::SetComp(node) => self.iterate(&node.generators),
            Expr::DictComp(node) => self.iterate(&node.generators),
            Expr::Generator(node) => self.iterate(&node.generators),
            Expr::Attribute(_) | Expr::Name(_) if self.judge(expr) => return,
            _ => {}
        }
        visitor::walk_expr(self, expr);
    }
}

/// What the file reads with `importlib` and `sys.modules`. A write, a subscript, an alias, a
/// `from` import or a value that is passed on ends the proof for that name.
pub(super) fn reads(module: &Module) -> Reads {
    let mut uses = Uses::default();
    uses.visit_body(&module.tree.body);
    Reads {
        importlib: !uses.importlib,
        sys_modules: !uses.sys_modules,
    }
}

/// True when the file has a `spec_from_file_location` call and each such use is a call with a
/// literal name that cannot name a module of the scan. An import statement is no use. A value use
/// (an alias) or a computed name ends the proof.
pub(super) fn foreign_specs<'a>(
    module: &Module,
    sites: impl Iterator<Item = &'a Site>,
    names: &HashSet<String>,
) -> bool {
    let mut calls = 0_usize;
    for site in sites {
        if !site.detail.ends_with("spec_from_file_location") || import_at(module, site.range) {
            continue;
        }
        let literal = call_at(module, site.range).and_then(spec_name);
        if !literal.is_some_and(|name| foreign(name, names)) {
            return false;
        }
        calls = calls.saturating_add(1);
    }
    calls > 0
}

/// The literal name of a `spec_from_file_location` call that gives only a name and a location. A
/// `loader` or `submodule_search_locations` can run the code of a file that the walk does not read.
fn spec_name(call: &ExprCall) -> Option<&Expr> {
    let args: &[Expr] = &call.arguments.args;
    let keywords: &[Keyword] = &call.arguments.keywords;
    let named = |key: &Keyword| {
        (key.arg.as_ref()).is_some_and(|arg| matches!(Identifier::as_str(arg), "name" | "location"))
    };
    let plain = args.len() + keywords.len() <= 2
        && args.iter().all(|arg| !Expr::is_starred_expr(arg))
        && keywords.iter().all(named);
    let name = args.first().or_else(|| {
        keywords.iter().find_map(|key| {
            (key.arg.as_ref().map(Identifier::as_str) == Some("name")).then_some(&key.value)
        })
    })?;
    (plain && matches!(name, Expr::StringLiteral(_))).then_some(name)
}

/// True when an import statement has the range.
fn import_at(module: &Module, range: TextRange) -> bool {
    struct Find(TextRange, bool);
    impl<'a> Visitor<'a> for Find {
        fn visit_stmt(&mut self, stmt: &'a Stmt) {
            self.1 |=
                matches!(stmt, Stmt::Import(_) | Stmt::ImportFrom(_)) && stmt.range() == self.0;
            visitor::walk_stmt(self, stmt);
        }
    }
    let mut find = Find(range, false);
    find.visit_body(&module.tree.body);
    find.1
}

/// True when the site cannot give a module of `names`.
pub(super) fn harmless(site: &Site, file: &File, names: &HashSet<String>) -> bool {
    let module = file.module;
    let detail: &str = &site.detail;
    let head = detail.split('.').next().unwrap_or_default();
    if (head == "importlib" && file.reads.importlib)
        || (detail == "sys.modules" && file.reads.sys_modules)
    {
        return true;
    }
    let loader_import = file.foreign_specs && LOADER_IMPORTS.contains(&detail);
    if loader_import && import_at(module, site.range) {
        return true;
    }
    let Some(call) = call_at(module, site.range) else {
        return false;
    };
    let last = detail.rsplit('.').next().unwrap_or_default();
    match last {
        "spec_from_file_location" => file.foreign_specs && spec_name(call).is_some(),
        call_name if LOADER_CALLS.contains(&call_name) => file.foreign_specs,
        "import_module" | "__import__" => {
            let args: &[Expr] = &call.arguments.args;
            let relative = last == "__import__"
                && (args.get(4).is_some() || call.arguments.find_keyword("level").is_some());
            let name =
                (args.first()).or_else(|| call.arguments.find_keyword("name").map(|k| &k.value));
            !relative && name.is_some_and(|name| foreign(name, names))
        }
        "exec" | "eval" | "compile" => match call.arguments.args.first() {
            Some(Expr::StringLiteral(text)) => inert(text.value.to_str()),
            _ => false,
        },
        _ => false,
    }
}

/// The modules of `names` that a string of `module` reaches (`native::reached`).
pub(super) fn named(module: &Module, names: &HashSet<String>) -> Vec<String> {
    struct Strings<'n>(&'n HashSet<String>, Vec<String>);
    impl<'a> Visitor<'a> for Strings<'_> {
        fn visit_expr(&mut self, expr: &'a Expr) {
            if let Expr::StringLiteral(text) = expr {
                self.1.extend(reached(text.value.to_str().trim(), self.0));
            }
            visitor::walk_expr(self, expr);
        }
    }
    let mut found = Strings(names, Vec::new());
    found.visit_body(&module.tree.body);
    found.1
}

/// The call whose callee is the expression at `range`.
fn call_at(module: &Module, range: TextRange) -> Option<&ExprCall> {
    struct Find<'a> {
        range: TextRange,
        found: Option<&'a ExprCall>,
    }
    impl<'a> Visitor<'a> for Find<'a> {
        fn visit_expr(&mut self, expr: &'a Expr) {
            match expr {
                Expr::Call(call) if call.func.range() == self.range => self.found = Some(call),
                _ => visitor::walk_expr(self, expr),
            }
        }
    }
    let mut find = Find { range, found: None };
    find.visit_body(&module.tree.body);
    find.found
}

/// True when each value that `expr` can have is no name of a module of `names`.
fn foreign(expr: &Expr, names: &HashSet<String>) -> bool {
    heads(expr).is_some_and(|heads| {
        heads.iter().all(|(head, exact)| {
            !head.starts_with('.')
                && (*exact || !String::is_empty(head))
                && !meets(head, *exact, names)
        })
    })
}

/// True when a name that is `head`, or that starts with `head`, can name a module of `names`.
fn meets(head: &str, exact: bool, names: &HashSet<String>) -> bool {
    names.iter().any(|name| {
        let under = head == name || head.starts_with(&format!("{name}."));
        let above = if exact {
            name.starts_with(&format!("{head}."))
        } else {
            name.starts_with(head)
        };
        under || above
    })
}

/// The texts that each value of `expr` is (`true`) or starts with (`false`); `None` when a value
/// can be any text.
fn heads(expr: &Expr) -> Option<Vec<(String, bool)>> {
    match expr {
        Expr::StringLiteral(text) => Some(vec![(text.value.to_str().to_owned(), true)]),
        Expr::FString(node) => Some(vec![(fstring_head(node), false)]),
        Expr::If(node) => {
            let mut found = heads(&node.body)?;
            found.extend(heads(&node.orelse)?);
            Some(found)
        }
        Expr::BinOp(node) if matches!(node.op, Operator::Add | Operator::Mod) => {
            let left = heads(&node.left)?;
            let cut = |text: &str| match node.op {
                Operator::Mod => text.split('%').next().unwrap_or_default().to_owned(),
                _ => text.to_owned(),
            };
            Some(
                left.into_iter()
                    .map(|(text, _)| (cut(&text), false))
                    .collect(),
            )
        }
        Expr::Call(node) => match &*node.func {
            Expr::Attribute(attribute) if Identifier::as_str(&attribute.attr) == "format" => {
                let Expr::StringLiteral(text) = &*attribute.value else {
                    return None;
                };
                let head = text.value.to_str().split('{').next().unwrap_or_default();
                Some(vec![(head.to_owned(), false)])
            }
            _ => None,
        },
        _ => None,
    }
}

/// The literal text before the first field of an f-string.
fn fstring_head(node: &ruff_python_ast::ExprFString) -> String {
    let mut head = String::new();
    for part in node.value.iter() {
        let open = match part {
            FStringPartRef::Literal(literal) => {
                head.push_str(&literal.value);
                true
            }
            FStringPartRef::FString(fstring) => literal_elements(&mut head, &fstring.elements),
        };
        if !open {
            break;
        }
    }
    head
}

/// Add the literal elements before the first field to `head`; `false` at a field.
fn literal_elements(head: &mut String, elements: &InterpolatedStringElements) -> bool {
    for element in elements.iter() {
        match element {
            InterpolatedStringElement::Literal(literal) => head.push_str(&literal.value),
            InterpolatedStringElement::Interpolation(_) => return false,
        }
    }
    true
}

/// True when the code `text` names nothing: each statement is `pass` or an expression without a
/// name, an attribute, a call or a subscript.
fn inert(text: &str) -> bool {
    struct Names(bool);
    impl<'a> Visitor<'a> for Names {
        fn visit_expr(&mut self, expr: &'a Expr) {
            self.0 |= matches!(
                expr,
                Expr::Name(_)
                    | Expr::Attribute(_)
                    | Expr::Call(_)
                    | Expr::Subscript(_)
                    | Expr::Named(_)
                    | Expr::Lambda(_)
            );
            visitor::walk_expr(self, expr);
        }
    }
    let Ok(tree) = parse(text, PyMinor::Py314) else {
        return false;
    };
    let mut names = Names(false);
    for stmt in &tree.body {
        match stmt {
            Stmt::Pass(_) => {}
            Stmt::Expr(node) => names.visit_expr(&node.value),
            _ => return false,
        }
    }
    !names.0
}
