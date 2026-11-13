// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Compiler lexical ownership and source binding sites, without a runtime resolver (AD-412).

use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::rc::Rc;

use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{Expr, ExprContext, Parameters, Stmt};
use ruff_text_size::{Ranged, TextRange};
use serde_json::{json, Value};

use super::scan::{Result, Scan};
use crate::module::{definition::Def, Module};
use crate::pyast::Node;

mod headers;
mod lookup;
mod nested;
mod summary;
mod visit;

#[derive(Clone, Copy, Default, PartialEq)]
enum Kind {
    #[default]
    Module,
    Function,
    Class,
    Comprehension,
    Parameters,
    Alias,
}

type Names = BTreeSet<String>;

#[derive(Default)]
struct Scope<'a> {
    node: Option<Node<'a>>,
    kind: Kind,
    qualified: Rc<str>,
    identity: Option<String>,
    parent: Option<usize>,
    table: bool,
    private_context: bool,
    inlined: bool,
    locals: Names,
    compiler_locals: Names,
    compiler_parent: Option<usize>,
    globals: Names,
    nonlocals: Names,
    free_names: Names,
    seen: Names,
    blocked: Names,
    bindings: BTreeMap<String, Vec<Site<'a>>>,
    summaries: BTreeMap<String, Summary>,
}

struct Summary {
    targets: Vec<String>,
    kind: String,
    uncertain: bool,
    earliest: Option<(i64, i64)>,
}

#[derive(Clone)]
struct Site<'a> {
    node: Node<'a>,
    conditional: bool,
}

struct Query<'a> {
    node: &'a Expr,
    scope: usize,
}

type SiteKey = (&'static str, i64, i64, i64);

struct Index<'a> {
    module: &'a Module,
    scopes: Vec<Scope<'a>>,
    queries: Vec<Query<'a>>,
    sites: Vec<(usize, String, Site<'a>)>,
    aliases: HashMap<(i64, i64, String), (String, String)>,
    numeric: BTreeSet<i64>,
    future: bool,
    children: HashMap<(usize, String, i64), usize>,
    touched: BTreeSet<usize>,
    generator_ranges: HashMap<*const Expr, TextRange>,
    tokens: crate::parse::fact_tokens::Tokens,
    hidden_tables: usize,
    nodes: Vec<(SiteKey, usize)>,
    by_site: HashMap<(&'static str, i64, i64), usize>,
    inline_scopes: Vec<usize>,
}

pub(super) fn collect(module: &Module, scan: &mut Scan, input: &Value) -> Result<Value> {
    let mut index = Index {
        module,
        scopes: Vec::new(),
        queries: Vec::new(),
        sites: Vec::new(),
        aliases: HashMap::new(),
        numeric: BTreeSet::new(),
        future: super::scan::future_annotations(scan, module)?,
        children: HashMap::new(),
        touched: BTreeSet::new(),
        generator_ranges: HashMap::new(),
        tokens: crate::parse::fact_tokens::tokens(module.text(), &mut scan.work)?,
        hidden_tables: 0,
        nodes: Vec::new(),
        by_site: HashMap::new(),
        inline_scopes: Vec::new(),
    };
    if let Some(aliases) = input.get("aliases") {
        let aliases = aliases.as_array().ok_or("invalid lexical aliases")?;
        for alias in aliases {
            scan.tick(1)?;
            let line = alias
                .get("line")
                .and_then(Value::as_i64)
                .ok_or("invalid alias line")?;
            let column = alias
                .get("column")
                .and_then(Value::as_i64)
                .ok_or("invalid alias column")?;
            let name = text(alias, "name")?;
            let target = text(alias, "target")?;
            let kind = text(alias, "kind")?;
            if !matches!(kind, "module" | "symbol") {
                return Err("invalid alias kind".into());
            }
            scan.tick(name.len().saturating_add(target.len()))?;
            index
                .aliases
                .insert((line, column, name.into()), (target.into(), kind.into()));
        }
    }
    index.scopes.push(Scope {
        qualified: Rc::from(module.name.as_str()),
        identity: Some(stable_id("MOD", &[Part::Text(&module.name)])),
        table: true,
        ..Scope::default()
    });
    index.by_site.insert(("Module", 1, 0), 0);
    index.body(scan, &module.tree.body, 0, false, 0)?;
    index.index_bindings(scan)?;
    index.dump(scan, input)
}

fn text<'a>(value: &'a Value, key: &str) -> Result<&'a str> {
    value
        .get(key)
        .and_then(Value::as_str)
        .ok_or_else(|| format!("invalid lexical {key}"))
}

impl<'a> Index<'a> {
    fn expression_range(&self, expr: &Expr) -> TextRange {
        self.generator_ranges
            .get(&std::ptr::from_ref(expr))
            .copied()
            .unwrap_or_else(|| expr.range())
    }

    fn generator_range(&mut self, scan: &mut Scan, expr: &'a Expr) -> Result<TextRange> {
        if let Some(range) = self.generator_ranges.get(&std::ptr::from_ref(expr)) {
            return Ok(*range);
        }
        let range = expr.range();
        if !matches!(expr, Expr::Generator(_)) {
            return Ok(range);
        }
        if self.tokens.parentheses.get(&range.start()) == Some(&range.end()) {
            self.generator_ranges
                .insert(std::ptr::from_ref(expr), range);
            return Ok(range);
        }
        use ruff_python_ast::token::TokenKind as T;
        let tokens = &self.tokens.significant;
        scan.tick(1)?;
        let before = tokens.partition_point(|(_, r)| r.end() <= range.start());
        let after = tokens.partition_point(|(_, r)| r.start() < range.end());
        let left = before.checked_sub(1).and_then(|i| tokens.get(i));
        let right = tokens.get(after);
        let found = match (left, right) {
            (Some((T::Lpar, l)), Some((T::Rpar, r))) => TextRange::new(l.start(), r.end()),
            _ => return Err("lexical generator wrapper unseen".into()),
        };
        self.generator_ranges
            .insert(std::ptr::from_ref(expr), found);
        Ok(found)
    }
    fn scope(&self, id: usize) -> Result<&Scope<'a>> {
        self.scopes
            .get(id)
            .ok_or_else(|| "lexical scope unseen".into())
    }

    fn scope_mut(&mut self, id: usize) -> Result<&mut Scope<'a>> {
        self.scopes
            .get_mut(id)
            .ok_or_else(|| "lexical scope unseen".into())
    }

    fn body(
        &mut self,
        scan: &mut Scan,
        body: &'a [Stmt],
        scope: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        for stmt in body {
            scan.tick(1)?;
            self.visit(scan, Node::Stmt(stmt), scope, conditional, true, depth + 1)?;
        }
        Ok(())
    }

    fn add(
        &mut self,
        scan: &mut Scan,
        scope: usize,
        name: &str,
        node: Node<'a>,
        conditional: bool,
    ) -> Result<()> {
        scan.tick(name.len())?;
        self.scope_mut(scope)?.locals.insert(name.into());
        self.scope_mut(scope)?.seen.insert(name.into());
        self.sites
            .push((scope, name.into(), Site { node, conditional }));
        Ok(())
    }

    fn enter(
        &mut self,
        scan: &mut Scan,
        node: Node<'a>,
        parent: usize,
        kind: Kind,
        name: &str,
        range: TextRange,
    ) -> Result<usize> {
        if kind == Kind::Function && name == "__annotate__" && scan.minor == PyMinor::Py314 {
            return Err("lexical annotation compiler child ambiguity".into());
        }
        let location = self.module.location(&range);
        let qualified = if matches!(kind, Kind::Function | Kind::Class) {
            scan.owner(&self.scope(parent)?.qualified, name)?
        } else {
            scan.owner(
                &self.scope(parent)?.qualified,
                &format!("<{name}:{}:{}>", location.line, location.column),
            )?
        };
        let identity = matches!(kind, Kind::Function | Kind::Class).then(|| {
            stable_id(
                "SYM",
                &[
                    Part::Text(&qualified),
                    Part::Text(&self.module.rel),
                    Part::Number(location.line),
                    Part::Number(location.column),
                ],
            )
        });
        let inlined = kind == Kind::Comprehension
            && name != "genexpr"
            && match scan.minor {
                PyMinor::Py311 => false,
                PyMinor::Py312 | PyMinor::Py313 | PyMinor::Py314 => true,
            }
            && (self.scope(parent)?.table || self.scope(parent)?.inlined);
        let mut compiler_parent = parent;
        while self.scope(compiler_parent)?.inlined {
            scan.tick(1)?;
            compiler_parent = self
                .scope(compiler_parent)?
                .parent
                .ok_or("inlined root unseen")?;
        }
        if !inlined
            && kind != Kind::Parameters
            && self
                .children
                .insert((compiler_parent, name.into(), location.line), 1)
                .is_some()
        {
            return Err("lexical compiler child ambiguity".into());
        }
        let table = !inlined && self.scope(compiler_parent)?.table && self.hidden_tables == 0;
        let private_context = match &node {
            Node::Stmt(Stmt::ClassDef(n)) => !n.name.trim_start_matches('_').is_empty(),
            _ => self.scope(parent)?.private_context,
        };
        let id = self.scopes.len();
        let compiler_parent = (inlined && self.hidden_tables == 0).then_some(compiler_parent);
        if compiler_parent.is_some() {
            self.inline_scopes.push(id);
        }
        self.scopes.push(Scope {
            node: Some(node),
            kind,
            qualified,
            identity,
            parent: Some(parent),
            table,
            private_context,
            inlined,
            compiler_parent,
            ..Scope::default()
        });
        Ok(id)
    }

    fn parameters(
        &mut self,
        scan: &mut Scan,
        params: Option<&'a Parameters>,
        scope: usize,
        conditional: bool,
    ) -> Result<()> {
        if let Some(params) = params {
            for p in params
                .posonlyargs
                .iter()
                .chain(&params.args)
                .chain(&params.kwonlyargs)
            {
                scan.tick(1)?;
                self.add(
                    scan,
                    scope,
                    p.parameter.name.as_str(),
                    Node::Arg(&p.parameter),
                    conditional,
                )?;
            }
            for p in params.vararg.iter().chain(&params.kwarg) {
                scan.tick(1)?;
                self.add(scan, scope, p.name.as_str(), Node::Arg(p), conditional)?;
            }
        }
        Ok(())
    }
}
