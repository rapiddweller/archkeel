// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One CPython node over the ruff tree, its class name and the names and texts of the contexts
//! and the operators (AD-377).

use std::rc::Rc;

use ruff_python_ast::{
    BoolOp, CmpOp, Comprehension, ElifElseClause, ExceptHandler, Expr, ExprContext, Keyword,
    MatchCase, Operator, Parameter, Parameters, Pattern, Stmt, TypeParam, TypeParams, UnaryOp,
    WithItem,
};

use super::fstring::Piece;

/// One CPython node over the ruff tree.
#[derive(Clone)]
pub enum Node<'a> {
    Stmt(&'a Stmt),
    /// An `elif` clause and the clauses after it: the CPython `If` in the `orelse` of the clause
    /// before it. The first clause has a test.
    Elif(&'a [ElifElseClause]),
    Expr(&'a Expr),
    Handler(&'a ExceptHandler),
    /// The `arguments` of a function or a lambda; a lambda without parameters has none.
    Arguments(Option<&'a Parameters>),
    Arg(&'a Parameter),
    Keyword(&'a Keyword),
    Alias,
    WithItem(&'a WithItem),
    MatchCase(&'a MatchCase),
    Pattern(&'a Pattern),
    Comprehension(&'a Comprehension),
    TypeParam(&'a TypeParam),
    /// The `JoinedStr` of a format spec.
    Spec(Rc<[Piece<'a>]>),
    /// One value of a `JoinedStr` or a `TemplateStr`.
    Piece(Rc<[Piece<'a>]>, usize),
    /// A context or an operator: a node without fields.
    Leaf(&'static str),
}

impl<'a> Node<'a> {
    /// The expression of an expression node.
    pub fn expr(&self) -> Option<&'a Expr> {
        match self {
            Node::Expr(expr) => Some(expr),
            _ => None,
        }
    }

    /// The class name, as `type(node).__name__`.
    pub fn kind(&self) -> &'static str {
        match self {
            Node::Stmt(stmt) => stmt_kind(stmt),
            Node::Elif(_) => "If",
            Node::Expr(expr) => expr_kind(expr),
            Node::Handler(_) => "ExceptHandler",
            Node::Arguments(_) => "arguments",
            Node::Arg(_) => "arg",
            Node::Keyword(_) => "keyword",
            Node::Alias => "alias",
            Node::WithItem(_) => "withitem",
            Node::MatchCase(_) => "match_case",
            Node::Pattern(pattern) => pattern_kind(pattern),
            Node::Comprehension(_) => "comprehension",
            Node::TypeParam(param) => match param {
                TypeParam::TypeVar(_) => "TypeVar",
                TypeParam::ParamSpec(_) => "ParamSpec",
                TypeParam::TypeVarTuple(_) => "TypeVarTuple",
            },
            Node::Spec(_) => "JoinedStr",
            Node::Piece(pieces, index) => pieces.get(*index).map_or("Constant", Piece::kind),
            Node::Leaf(name) => name,
        }
    }
}

fn stmt_kind(stmt: &Stmt) -> &'static str {
    match stmt {
        Stmt::FunctionDef(node) if node.is_async => "AsyncFunctionDef",
        Stmt::FunctionDef(_) => "FunctionDef",
        Stmt::ClassDef(_) => "ClassDef",
        Stmt::Return(_) => "Return",
        Stmt::Delete(_) => "Delete",
        Stmt::TypeAlias(_) => "TypeAlias",
        Stmt::Assign(_) => "Assign",
        Stmt::AugAssign(_) => "AugAssign",
        Stmt::AnnAssign(_) => "AnnAssign",
        Stmt::For(node) if node.is_async => "AsyncFor",
        Stmt::For(_) => "For",
        Stmt::While(_) => "While",
        Stmt::If(_) => "If",
        Stmt::With(node) if node.is_async => "AsyncWith",
        Stmt::With(_) => "With",
        Stmt::Match(_) => "Match",
        Stmt::Raise(_) => "Raise",
        Stmt::Try(node) if node.is_star => "TryStar",
        Stmt::Try(_) => "Try",
        Stmt::Assert(_) => "Assert",
        Stmt::Import(_) => "Import",
        Stmt::ImportFrom(_) => "ImportFrom",
        Stmt::Global(_) => "Global",
        Stmt::Nonlocal(_) => "Nonlocal",
        Stmt::Expr(_) => "Expr",
        Stmt::Pass(_) => "Pass",
        Stmt::Break(_) => "Break",
        Stmt::Continue(_) => "Continue",
        Stmt::IpyEscapeCommand(_) => "IpyEscapeCommand",
    }
}

fn expr_kind(expr: &Expr) -> &'static str {
    match expr {
        Expr::BoolOp(_) => "BoolOp",
        Expr::Named(_) => "NamedExpr",
        Expr::BinOp(_) => "BinOp",
        Expr::UnaryOp(_) => "UnaryOp",
        Expr::Lambda(_) => "Lambda",
        Expr::If(_) => "IfExp",
        Expr::Dict(_) => "Dict",
        Expr::Set(_) => "Set",
        Expr::ListComp(_) => "ListComp",
        Expr::SetComp(_) => "SetComp",
        Expr::DictComp(_) => "DictComp",
        Expr::Generator(_) => "GeneratorExp",
        Expr::Await(_) => "Await",
        Expr::Yield(_) => "Yield",
        Expr::YieldFrom(_) => "YieldFrom",
        Expr::Compare(_) => "Compare",
        Expr::Call(_) => "Call",
        Expr::FString(_) => "JoinedStr",
        Expr::TString(_) => "TemplateStr",
        Expr::StringLiteral(_)
        | Expr::BytesLiteral(_)
        | Expr::NumberLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::NoneLiteral(_)
        | Expr::EllipsisLiteral(_) => "Constant",
        Expr::Attribute(_) => "Attribute",
        Expr::Subscript(_) => "Subscript",
        Expr::Starred(_) => "Starred",
        Expr::Name(_) => "Name",
        Expr::List(_) => "List",
        Expr::Tuple(_) => "Tuple",
        Expr::Slice(_) => "Slice",
        Expr::IpyEscapeCommand(_) => "IpyEscapeCommand",
    }
}

fn pattern_kind(pattern: &Pattern) -> &'static str {
    match pattern {
        Pattern::MatchValue(_) => "MatchValue",
        Pattern::MatchSingleton(_) => "MatchSingleton",
        Pattern::MatchSequence(_) => "MatchSequence",
        Pattern::MatchMapping(_) => "MatchMapping",
        Pattern::MatchClass(_) => "MatchClass",
        Pattern::MatchStar(_) => "MatchStar",
        Pattern::MatchAs(_) => "MatchAs",
        Pattern::MatchOr(_) => "MatchOr",
    }
}

/// The class name of a context: `Load`, `Store` or `Del`.
pub fn context(ctx: ExprContext) -> &'static str {
    match ctx {
        ExprContext::Store => "Store",
        ExprContext::Del => "Del",
        ExprContext::Load | ExprContext::Invalid => "Load",
    }
}

/// The class name and the source text of a binary operator.
pub fn operator(op: Operator) -> (&'static str, &'static str) {
    match op {
        Operator::Add => ("Add", "+"),
        Operator::Sub => ("Sub", "-"),
        Operator::Mult => ("Mult", "*"),
        Operator::MatMult => ("MatMult", "@"),
        Operator::Div => ("Div", "/"),
        Operator::Mod => ("Mod", "%"),
        Operator::Pow => ("Pow", "**"),
        Operator::LShift => ("LShift", "<<"),
        Operator::RShift => ("RShift", ">>"),
        Operator::BitOr => ("BitOr", "|"),
        Operator::BitXor => ("BitXor", "^"),
        Operator::BitAnd => ("BitAnd", "&"),
        Operator::FloorDiv => ("FloorDiv", "//"),
    }
}

/// The class name and the source text of a Boolean operator.
pub fn bool_op(op: BoolOp) -> (&'static str, &'static str) {
    match op {
        BoolOp::And => ("And", "and"),
        BoolOp::Or => ("Or", "or"),
    }
}

/// The class name and the source text of a unary operator.
pub fn unary_op(op: UnaryOp) -> (&'static str, &'static str) {
    match op {
        UnaryOp::Invert => ("Invert", "~"),
        UnaryOp::Not => ("Not", "not "),
        UnaryOp::UAdd => ("UAdd", "+"),
        UnaryOp::USub => ("USub", "-"),
    }
}

/// The class name and the source text of a comparison operator.
pub fn cmp_op(op: CmpOp) -> (&'static str, &'static str) {
    match op {
        CmpOp::Eq => ("Eq", "=="),
        CmpOp::NotEq => ("NotEq", "!="),
        CmpOp::Lt => ("Lt", "<"),
        CmpOp::LtE => ("LtE", "<="),
        CmpOp::Gt => ("Gt", ">"),
        CmpOp::GtE => ("GtE", ">="),
        CmpOp::Is => ("Is", "is"),
        CmpOp::IsNot => ("IsNot", "is not"),
        CmpOp::In => ("In", "in"),
        CmpOp::NotIn => ("NotIn", "not in"),
    }
}

/// The type parameters of a definition, empty without brackets.
pub fn type_params(params: Option<&TypeParams>) -> &[TypeParam] {
    params.map_or(&[], |params| params.type_params.as_slice())
}
