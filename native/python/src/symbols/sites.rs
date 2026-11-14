// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `source.definition_sites`: each class and function of a module, its lexical parent and the
//! control flow around it, in the order of the Python generator (depth first, in field order).
//!
//! The walk reads only the statement lists of a node (`body`, `orelse`, `handlers`, `finalbody`
//! and `cases`), so it never enters an expression. It keeps its work on a heap stack.

use std::rc::Rc;

use ruff_python_ast::{ElifElseClause, ExceptHandler, MatchCase, Stmt};
use ruff_text_size::{Ranged, TextRange, TextSize};

pub(super) use crate::module::definition::Def;

/// One control-flow context of a definition (`DefinitionFrame`).
#[derive(Clone)]
pub(super) struct Context {
    pub kind: &'static str,
    pub branch: &'static str,
    /// The range of the site: the statement, the `except` handler or the pattern of a case.
    pub site: TextRange,
}

pub(super) struct Site<'a> {
    pub def: Def<'a>,
    /// The index of the lexical parent in the list of sites.
    pub parent: Option<usize>,
    pub contexts: Rc<[Context]>,
}

enum Item<'a> {
    Stmt(&'a Stmt),
    Elif(&'a [ElifElseClause]),
    Handler(&'a ExceptHandler),
    Case(&'a MatchCase),
}

struct Work<'a> {
    item: Item<'a>,
    parent: Option<usize>,
    contexts: Rc<[Context]>,
}

/// The definition sites of a module body, in the order of `definition_sites`.
pub(super) fn sites(body: &[Stmt]) -> Vec<Site<'_>> {
    let mut found = Vec::new();
    let mut stack: Vec<Work<'_>> = Vec::new();
    let empty: Rc<[Context]> = Rc::from(Vec::new());
    push_stmts(&mut stack, body, None, &empty);
    while let Some(work) = stack.pop() {
        visit(work, &mut found, &mut stack);
    }
    found
}

fn push_stmts<'a>(
    stack: &mut Vec<Work<'a>>,
    stmts: &'a [Stmt],
    parent: Option<usize>,
    contexts: &Rc<[Context]>,
) {
    for stmt in stmts.iter().rev() {
        stack.push(Work {
            item: Item::Stmt(stmt),
            parent,
            contexts: Rc::clone(contexts),
        });
    }
}

/// The children of one control-flow node, in field order: each list with its branch.
struct Branches<'a> {
    kind: &'static str,
    site: TextRange,
    lists: Vec<(&'static str, Vec<Item<'a>>)>,
}

fn visit<'a>(work: Work<'a>, found: &mut Vec<Site<'a>>, stack: &mut Vec<Work<'a>>) {
    let Work {
        item,
        parent,
        contexts,
    } = work;
    let branches = match item {
        Item::Stmt(Stmt::FunctionDef(node)) => {
            return define(Def::Function(node), parent, contexts, found, stack)
        }
        Item::Stmt(Stmt::ClassDef(node)) => {
            return define(Def::Class(node), parent, contexts, found, stack)
        }
        Item::Stmt(stmt) => match branches_of(stmt) {
            Some(branches) => branches,
            None => return,
        },
        Item::Elif(clauses) => elif(clauses),
        Item::Handler(ExceptHandler::ExceptHandler(handler)) => {
            return push_stmts(stack, &handler.body, parent, &contexts);
        }
        Item::Case(case) => return push_stmts(stack, &case.body, parent, &contexts),
    };
    let mut pending = Vec::new();
    for (branch, items) in branches.lists {
        for item in items {
            let site = match &item {
                Item::Handler(handler) => handler.range(),
                Item::Case(case) => case.pattern.range(),
                _ => branches.site,
            };
            let mut nested: Vec<Context> = contexts.to_vec();
            nested.push(Context {
                kind: branches.kind,
                branch,
                site,
            });
            pending.push(Work {
                item,
                parent,
                contexts: Rc::from(nested),
            });
        }
    }
    stack.extend(pending.into_iter().rev());
}

fn define<'a>(
    def: Def<'a>,
    parent: Option<usize>,
    contexts: Rc<[Context]>,
    found: &mut Vec<Site<'a>>,
    stack: &mut Vec<Work<'a>>,
) {
    let index = found.len();
    found.push(Site {
        def,
        parent,
        contexts: Rc::clone(&contexts),
    });
    push_stmts(stack, def.body(), Some(index), &contexts);
}

fn stmts(items: &[Stmt]) -> Vec<Item<'_>> {
    items.iter().map(Item::Stmt).collect()
}

/// The `orelse` of an `If`: the `If` of the next `elif`, or the body of the `else`.
fn orelse(clauses: &[ElifElseClause]) -> Vec<Item<'_>> {
    match clauses.first() {
        Some(clause) if clause.test.is_some() => vec![Item::Elif(clauses)],
        Some(clause) => stmts(&clause.body),
        None => Vec::new(),
    }
}

fn elif(clauses: &[ElifElseClause]) -> Branches<'_> {
    let (body, rest) = match clauses.split_first() {
        Some((clause, rest)) => (stmts(&clause.body), rest),
        None => (Vec::new(), clauses),
    };
    let start = clauses.first().map_or(TextSize::default(), Ranged::start);
    let end = clauses.last().map_or(start, Ranged::end);
    Branches {
        kind: "if",
        site: TextRange::new(start, end),
        lists: vec![("body", body), ("else", orelse(rest))],
    }
}

fn branches_of(stmt: &Stmt) -> Option<Branches<'_>> {
    let (kind, lists) = match stmt {
        Stmt::If(node) => (
            "if",
            vec![
                ("body", stmts(&node.body)),
                ("else", orelse(&node.elif_else_clauses)),
            ],
        ),
        Stmt::For(node) => (
            if node.is_async { "async_for" } else { "for" },
            vec![("body", stmts(&node.body)), ("else", stmts(&node.orelse))],
        ),
        Stmt::While(node) => (
            "while",
            vec![("body", stmts(&node.body)), ("else", stmts(&node.orelse))],
        ),
        Stmt::With(node) => (
            if node.is_async { "async_with" } else { "with" },
            vec![("body", stmts(&node.body))],
        ),
        Stmt::Try(node) => (
            if node.is_star { "try_star" } else { "try" },
            vec![
                ("body", stmts(&node.body)),
                ("handler", node.handlers.iter().map(Item::Handler).collect()),
                ("else", stmts(&node.orelse)),
                ("finally", stmts(&node.finalbody)),
            ],
        ),
        Stmt::Match(node) => (
            "match",
            vec![("case", node.cases.iter().map(Item::Case).collect())],
        ),
        _ => return None,
    };
    Some(Branches {
        kind,
        site: stmt.range(),
        lists,
    })
}
