// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `ast.iter_child_nodes` of each CPython node: the nodes of its fields in the order of `_fields`
//! (Python 3.11 to 3.14). A field that holds a `str`, an `int` or `None` gives no node.

use std::rc::Rc;

use ruff_python_ast::{ElifElseClause, ExceptHandler, Expr, Pattern, Stmt, TypeParam};

use super::fstring::{self, Piece};
use super::node::{bool_op, cmp_op, context, operator, type_params, unary_op, Node};

/// `ast.iter_child_nodes`: the child nodes in the order of `_fields`.
pub(crate) fn child_nodes<'a>(
    node: &Node<'a>,
    minor: archkeel_facts::pyminor::PyMinor,
) -> Vec<Node<'a>> {
    let mut out = Vec::new();
    match node {
        Node::Stmt(stmt) => stmt_children(stmt, minor, &mut out),
        Node::Elif(clauses) => elif_children(clauses, &mut out),
        Node::Expr(expr) => expr_children(expr, &mut out),
        Node::Handler(ExceptHandler::ExceptHandler(handler)) => {
            exprs(&mut out, handler.type_.as_deref());
            stmts(&mut out, &handler.body);
        }
        Node::Arguments(params) => arguments(*params, &mut out),
        Node::Arg(arg) => exprs(&mut out, arg.annotation.as_deref()),
        Node::Keyword(keyword) => out.push(Node::Expr(&keyword.value)),
        Node::WithItem(item) => {
            out.push(Node::Expr(&item.context_expr));
            exprs(&mut out, item.optional_vars.as_deref());
        }
        Node::MatchCase(case) => {
            out.push(Node::Pattern(&case.pattern));
            exprs(&mut out, case.guard.as_deref());
            stmts(&mut out, &case.body);
        }
        Node::Pattern(pattern) => pattern_children(pattern, &mut out),
        Node::Comprehension(generator) => {
            out.push(Node::Expr(&generator.target));
            out.push(Node::Expr(&generator.iter));
            exprs(&mut out, &generator.ifs);
        }
        Node::TypeParam(param) => type_param_children(param, minor, &mut out),
        Node::Spec(pieces) => pieces_of(pieces, &mut out),
        Node::Piece(pieces, index) => {
            if let Some(Piece::Value { expr, spec, .. }) = pieces.get(*index) {
                out.push(Node::Expr(expr));
                if let Some(spec) = spec {
                    out.push(Node::Spec(Rc::clone(spec)));
                }
            }
        }
        Node::Alias | Node::Leaf(_) => {}
    }
    out
}

fn exprs<'a>(out: &mut Vec<Node<'a>>, items: impl IntoIterator<Item = &'a Expr>) {
    out.extend(items.into_iter().map(Node::Expr));
}

/// An operand, an operator and an operand: `AugAssign` and `BinOp`.
fn operation<'a>(out: &mut Vec<Node<'a>>, left: &'a Expr, op: &'static str, right: &'a Expr) {
    out.push(Node::Expr(left));
    out.push(Node::Leaf(op));
    out.push(Node::Expr(right));
}

fn stmts<'a>(out: &mut Vec<Node<'a>>, items: &'a [Stmt]) {
    out.extend(items.iter().map(Node::Stmt));
}

fn params<'a>(
    out: &mut Vec<Node<'a>>,
    minor: archkeel_facts::pyminor::PyMinor,
    items: &'a [TypeParam],
) {
    if match minor {
        archkeel_facts::pyminor::PyMinor::Py311 => false,
        archkeel_facts::pyminor::PyMinor::Py312
        | archkeel_facts::pyminor::PyMinor::Py313
        | archkeel_facts::pyminor::PyMinor::Py314 => true,
    } {
        out.extend(items.iter().map(Node::TypeParam));
    }
}

fn pieces_of<'a>(pieces: &Rc<[Piece<'a>]>, out: &mut Vec<Node<'a>>) {
    out.extend((0..pieces.len()).map(|index| Node::Piece(Rc::clone(pieces), index)));
}

fn stmt_children<'a>(
    stmt: &'a Stmt,
    minor: archkeel_facts::pyminor::PyMinor,
    out: &mut Vec<Node<'a>>,
) {
    match stmt {
        Stmt::FunctionDef(node) => {
            out.push(Node::Arguments(Some(&node.parameters)));
            stmts(out, &node.body);
            exprs(out, node.decorator_list.iter().map(|item| &item.expression));
            exprs(out, node.returns.as_deref());
            params(out, minor, type_params(node.type_params.as_deref()));
        }
        Stmt::ClassDef(node) => {
            if let Some(arguments) = &node.arguments {
                exprs(out, arguments.args.iter());
                out.extend(arguments.keywords.iter().map(Node::Keyword));
            }
            stmts(out, &node.body);
            exprs(out, node.decorator_list.iter().map(|item| &item.expression));
            params(out, minor, type_params(node.type_params.as_deref()));
        }
        Stmt::Return(node) => exprs(out, node.value.as_deref()),
        Stmt::Delete(node) => exprs(out, &node.targets),
        Stmt::TypeAlias(node) => {
            out.push(Node::Expr(&node.name));
            params(out, minor, type_params(node.type_params.as_deref()));
            out.push(Node::Expr(&node.value));
        }
        Stmt::Assign(node) => {
            exprs(out, &node.targets);
            out.push(Node::Expr(&node.value));
        }
        Stmt::AugAssign(node) => operation(out, &node.target, operator(node.op).0, &node.value),
        Stmt::AnnAssign(node) => {
            out.push(Node::Expr(&node.target));
            out.push(Node::Expr(&node.annotation));
            exprs(out, node.value.as_deref());
        }
        Stmt::For(node) => {
            out.push(Node::Expr(&node.target));
            out.push(Node::Expr(&node.iter));
            stmts(out, &node.body);
            stmts(out, &node.orelse);
        }
        Stmt::While(node) => {
            out.push(Node::Expr(&node.test));
            stmts(out, &node.body);
            stmts(out, &node.orelse);
        }
        Stmt::If(node) => {
            out.push(Node::Expr(&node.test));
            stmts(out, &node.body);
            orelse(&node.elif_else_clauses, out);
        }
        Stmt::With(node) => {
            out.extend(node.items.iter().map(Node::WithItem));
            stmts(out, &node.body);
        }
        Stmt::Match(node) => {
            out.push(Node::Expr(&node.subject));
            out.extend(node.cases.iter().map(Node::MatchCase));
        }
        Stmt::Raise(node) => {
            exprs(out, node.exc.as_deref());
            exprs(out, node.cause.as_deref());
        }
        Stmt::Try(node) => {
            stmts(out, &node.body);
            out.extend(node.handlers.iter().map(Node::Handler));
            stmts(out, &node.orelse);
            stmts(out, &node.finalbody);
        }
        Stmt::Assert(node) => {
            out.push(Node::Expr(&node.test));
            exprs(out, node.msg.as_deref());
        }
        Stmt::Import(node) => out.extend(node.names.iter().map(|_| Node::Alias)),
        Stmt::ImportFrom(node) => out.extend(node.names.iter().map(|_| Node::Alias)),
        Stmt::Expr(node) => out.push(Node::Expr(&node.value)),
        Stmt::Global(_)
        | Stmt::Nonlocal(_)
        | Stmt::Pass(_)
        | Stmt::Break(_)
        | Stmt::Continue(_)
        | Stmt::IpyEscapeCommand(_) => {}
    }
}

/// The `orelse` of an `If`: the `If` of the next `elif`, or the body of the `else`.
pub(super) fn orelse<'a>(clauses: &'a [ElifElseClause], out: &mut Vec<Node<'a>>) {
    match clauses.first() {
        Some(clause) if clause.test.is_some() => out.push(Node::Elif(clauses)),
        Some(clause) => stmts(out, &clause.body),
        None => {}
    }
}

fn elif_children<'a>(clauses: &'a [ElifElseClause], out: &mut Vec<Node<'a>>) {
    let Some((clause, rest)) = clauses.split_first() else {
        return;
    };
    exprs(out, clause.test.as_ref());
    stmts(out, &clause.body);
    orelse(rest, out);
}

fn expr_children<'a>(expr: &'a Expr, out: &mut Vec<Node<'a>>) {
    match expr {
        Expr::BoolOp(node) => {
            out.push(Node::Leaf(bool_op(node.op).0));
            exprs(out, &node.values);
        }
        Expr::Named(node) => exprs(out, [&*node.target, &*node.value]),
        Expr::BinOp(node) => operation(out, &node.left, operator(node.op).0, &node.right),
        Expr::UnaryOp(node) => {
            out.push(Node::Leaf(unary_op(node.op).0));
            out.push(Node::Expr(&node.operand));
        }
        Expr::Lambda(node) => {
            out.push(Node::Arguments(node.parameters.as_deref()));
            out.push(Node::Expr(&node.body));
        }
        Expr::If(node) => exprs(out, [&*node.test, &*node.body, &*node.orelse]),
        Expr::Dict(node) => {
            exprs(out, node.items.iter().filter_map(|item| item.key.as_ref()));
            exprs(out, node.items.iter().map(|item| &item.value));
        }
        Expr::Set(node) => exprs(out, &node.elts),
        Expr::ListComp(node) => comprehension(out, &node.elt, &node.generators),
        Expr::SetComp(node) => comprehension(out, &node.elt, &node.generators),
        Expr::Generator(node) => comprehension(out, &node.elt, &node.generators),
        Expr::DictComp(node) => {
            exprs(out, node.key.as_deref());
            comprehension(out, &node.value, &node.generators);
        }
        Expr::Await(node) => out.push(Node::Expr(&node.value)),
        Expr::Yield(node) => exprs(out, node.value.as_deref()),
        Expr::YieldFrom(node) => out.push(Node::Expr(&node.value)),
        Expr::Compare(node) => compare(out, &node.operands, &node.ops),
        Expr::Call(node) => {
            out.push(Node::Expr(&node.func));
            exprs(out, node.arguments.args.iter());
            out.extend(node.arguments.keywords.iter().map(Node::Keyword));
        }
        Expr::FString(node) => pieces_of(&fstring::fstring(&node.value), out),
        Expr::TString(node) => pieces_of(&fstring::tstring(&node.value), out),
        Expr::Attribute(node) => {
            out.push(Node::Expr(&node.value));
            out.push(Node::Leaf(context(node.ctx)));
        }
        Expr::Subscript(node) => {
            exprs(out, [&*node.value, &*node.slice]);
            out.push(Node::Leaf(context(node.ctx)));
        }
        Expr::Starred(node) => {
            out.push(Node::Expr(&node.value));
            out.push(Node::Leaf(context(node.ctx)));
        }
        Expr::Name(node) => out.push(Node::Leaf(context(node.ctx))),
        Expr::List(node) => {
            exprs(out, &node.elts);
            out.push(Node::Leaf(context(node.ctx)));
        }
        Expr::Tuple(node) => {
            exprs(out, &node.elts);
            out.push(Node::Leaf(context(node.ctx)));
        }
        Expr::Slice(node) => {
            exprs(out, node.lower.as_deref());
            exprs(out, node.upper.as_deref());
            exprs(out, node.step.as_deref());
        }
        _ => {}
    }
}

fn comprehension<'a>(
    out: &mut Vec<Node<'a>>,
    elt: &'a Expr,
    generators: &'a [ruff_python_ast::Comprehension],
) {
    out.push(Node::Expr(elt));
    out.extend(generators.iter().map(Node::Comprehension));
}

fn compare<'a>(out: &mut Vec<Node<'a>>, operands: &'a [Expr], ops: &[ruff_python_ast::CmpOp]) {
    let Some((left, comparators)) = operands.split_first() else {
        return;
    };
    out.push(Node::Expr(left));
    out.extend(ops.iter().map(|op| Node::Leaf(cmp_op(*op).0)));
    exprs(out, comparators);
}

/// `arguments`: `posonlyargs`, `args`, `vararg`, `kwonlyargs`, `kw_defaults` (without `None`),
/// `kwarg` and `defaults`.
fn arguments<'a>(params: Option<&'a ruff_python_ast::Parameters>, out: &mut Vec<Node<'a>>) {
    let Some(params) = params else {
        return;
    };
    out.extend(
        params
            .posonlyargs
            .iter()
            .map(|item| Node::Arg(&item.parameter)),
    );
    out.extend(params.args.iter().map(|item| Node::Arg(&item.parameter)));
    out.extend(params.vararg.as_deref().map(Node::Arg));
    out.extend(
        params
            .kwonlyargs
            .iter()
            .map(|item| Node::Arg(&item.parameter)),
    );
    exprs(
        out,
        params
            .kwonlyargs
            .iter()
            .filter_map(|item| item.default.as_deref()),
    );
    out.extend(params.kwarg.as_deref().map(Node::Arg));
    let positional = params.posonlyargs.iter().chain(&params.args);
    exprs(out, positional.filter_map(|item| item.default.as_deref()));
}

fn pattern_children<'a>(pattern: &'a Pattern, out: &mut Vec<Node<'a>>) {
    let patterns = |out: &mut Vec<Node<'a>>, items: &'a [Pattern]| {
        out.extend(items.iter().map(Node::Pattern));
    };
    match pattern {
        Pattern::MatchValue(node) => out.push(Node::Expr(&node.value)),
        Pattern::MatchSequence(node) => patterns(out, &node.patterns),
        Pattern::MatchMapping(node) => {
            exprs(out, &node.keys);
            patterns(out, &node.patterns);
        }
        Pattern::MatchClass(node) => {
            out.push(Node::Expr(&node.cls));
            patterns(out, &node.arguments.patterns);
            out.extend(
                node.arguments
                    .keywords
                    .iter()
                    .map(|item| Node::Pattern(&item.pattern)),
            );
        }
        Pattern::MatchAs(node) => out.extend(node.pattern.as_deref().map(Node::Pattern)),
        Pattern::MatchOr(node) => patterns(out, &node.patterns),
        Pattern::MatchSingleton(_) | Pattern::MatchStar(_) => {}
    }
}

/// `TypeVar` (`name`, `bound`, `default_value`), `ParamSpec` and `TypeVarTuple` (`name`,
/// `default_value`). The default exists from 3.13 on.
fn type_param_children<'a>(
    param: &'a TypeParam,
    minor: archkeel_facts::pyminor::PyMinor,
    out: &mut Vec<Node<'a>>,
) {
    let default = match param {
        TypeParam::TypeVar(node) => {
            exprs(out, node.bound.as_deref());
            node.default.as_deref()
        }
        TypeParam::ParamSpec(node) => node.default.as_deref(),
        TypeParam::TypeVarTuple(node) => node.default.as_deref(),
    };
    if match minor {
        archkeel_facts::pyminor::PyMinor::Py311 | archkeel_facts::pyminor::PyMinor::Py312 => false,
        archkeel_facts::pyminor::PyMinor::Py313 | archkeel_facts::pyminor::PyMinor::Py314 => true,
    } {
        exprs(out, default);
    }
}
