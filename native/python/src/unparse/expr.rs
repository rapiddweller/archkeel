// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The expressions of `_Unparser`, and `_Precedence`. They recurse into one another, so they are
//! one module.
//!
//! A parent sets the precedence of a child before it writes it; a child that no parent set has
//! `TEST`. A node writes parentheses when its precedence is higher than the precedence that its
//! own operator needs (`require_parens`).

use ruff_python_ast::{
    BoolOp, Comprehension, Expr, ExprBinOp, ExprCall, ExprCompare, ExprDict, ExprIf, ExprLambda,
    ExprSlice, Number, Operator, Parameters, UnaryOp,
};

use crate::pyast::{bool_op, cmp_op, operator, unary_op};

use super::hazard::string_failure;
use super::literal;
use super::outcome::{Prec, TextFailure as Failure, MAX_DEPTH};
use super::writer::Writer;

/// `binop_precedence`, keyed by the text of the operator as in CPython.
fn binary_precedence(text: &str) -> Prec {
    match text {
        "+" | "-" => Prec::Arith,
        "<<" | ">>" => Prec::Shift,
        "|" => Prec::Expr,
        "^" => Prec::BXor,
        "&" => Prec::BAnd,
        "**" => Prec::Power,
        _ => Prec::Term,
    }
}

impl Writer<'_> {
    /// `traverse` of an expression whose parent set the precedence `prec`.
    pub(super) fn expr(&mut self, expr: &Expr, prec: Prec) -> Result<(), Failure> {
        self.depth += 1;
        if self.depth > MAX_DEPTH {
            return Err(Failure::Deep);
        }
        let result = self.dispatch(expr, prec);
        self.depth -= 1;
        result
    }

    /// The text of an expression in a field of an f-string, one level deeper than this writer.
    fn field_text(&self, expr: &Expr) -> Result<String, Failure> {
        let mut writer = self.inner();
        writer.expr(expr, Prec::Or)?;
        Ok(writer.out)
    }

    pub(super) fn dispatch(&mut self, expr: &Expr, prec: Prec) -> Result<(), Failure> {
        if let Some(failure) = string_failure(expr, self.source, self.minor) {
            return Err(failure);
        }
        match expr {
            Expr::Name(node) => self.write(node.id.as_str()),
            Expr::StringLiteral(node) => self.string(node)?,
            Expr::BytesLiteral(node) => {
                let bytes: Vec<u8> = node.value.bytes().collect();
                self.write(&literal::repr_bytes(&bytes));
            }
            Expr::NumberLiteral(node) => self.number(&node.value)?,
            Expr::BooleanLiteral(node) => self.write(if node.value { "True" } else { "False" }),
            Expr::NoneLiteral(_) => self.write("None"),
            Expr::EllipsisLiteral(_) => self.write("..."),
            Expr::FString(node) => {
                let pieces = crate::pyast::fstring::fstring(&node.value);
                let field = self.inner();
                self.ftext(&pieces, "f", &|expr| field.field_text(expr))?;
            }
            Expr::TString(node) => {
                let pieces = crate::pyast::fstring::tstring(&node.value);
                let field = self.inner();
                self.ftext(&pieces, "t", &|expr| field.field_text(expr))?;
            }
            Expr::IpyEscapeCommand(_) => return Err(Failure::Invalid),
            _ => self.compound(expr, prec)?,
        }
        Ok(())
    }

    /// `interleave(", ", traverse, items)` with the default precedence.
    pub(super) fn items(&mut self, items: &[Expr]) -> Result<(), Failure> {
        for (index, item) in items.iter().enumerate() {
            if index > 0 {
                self.write(", ");
            }
            self.expr(item, Prec::Test)?;
        }
        Ok(())
    }

    /// `items_view`: one item takes a trailing comma.
    pub(super) fn items_view(&mut self, items: &[Expr]) -> Result<(), Failure> {
        if let [item] = items {
            self.expr(item, Prec::Test)?;
            self.write(",");
            Ok(())
        } else {
            self.items(items)
        }
    }

    /// `visit_arguments`.
    pub(super) fn arguments(&mut self, params: &Parameters) -> Result<(), Failure> {
        let mut first = true;
        let positional = params.posonlyargs.len();
        for (index, param) in params.posonlyargs.iter().chain(&params.args).enumerate() {
            if !first {
                self.write(", ");
            }
            first = false;
            self.arg(&param.parameter)?;
            if let Some(default) = &param.default {
                self.write("=");
                self.expr(default, Prec::Test)?;
            }
            if index + 1 == positional {
                self.write(", /");
            }
        }
        if params.vararg.is_some() || !params.kwonlyargs.is_empty() {
            if !first {
                self.write(", ");
            }
            first = false;
            self.write("*");
            if let Some(vararg) = &params.vararg {
                self.arg(vararg)?;
            }
        }
        for param in &params.kwonlyargs {
            self.write(", ");
            self.arg(&param.parameter)?;
            if let Some(default) = &param.default {
                self.write("=");
                self.expr(default, Prec::Test)?;
            }
        }
        if let Some(kwarg) = &params.kwarg {
            if !first {
                self.write(", ");
            }
            self.write("**");
            self.arg(kwarg)?;
        }
        Ok(())
    }

    /// `visit_arg`: the name and its annotation.
    pub(super) fn arg(&mut self, param: &ruff_python_ast::Parameter) -> Result<(), Failure> {
        self.write(param.name.as_str());
        if let Some(annotation) = &param.annotation {
            self.write(": ");
            self.expr(annotation, Prec::Test)?;
        }
        Ok(())
    }

    /// `require_parens`: open a parenthesis when the precedence of the node is higher than the
    /// precedence that its operator needs.
    fn open(&mut self, prec: Prec, needed: Prec) -> bool {
        let open = prec > needed;
        if open {
            self.write("(");
        }
        open
    }

    fn close(&mut self, open: bool) {
        if open {
            self.write(")");
        }
    }

    pub(super) fn compound(&mut self, expr: &Expr, prec: Prec) -> Result<(), Failure> {
        match expr {
            Expr::BinOp(node) => self.binary(node, prec),
            Expr::UnaryOp(node) => self.unary(node.op, &node.operand, prec),
            Expr::BoolOp(node) => self.bool_op(node.op, &node.values, prec),
            Expr::Compare(node) => self.compare(node, prec),
            Expr::If(node) => self.conditional(node, prec),
            Expr::Lambda(node) => self.lambda(node, prec),
            Expr::Named(node) => {
                let open = self.open(prec, Prec::NamedExpr);
                self.expr(&node.target, Prec::Atom)?;
                self.write(" := ");
                self.expr(&node.value, Prec::Atom)?;
                self.close(open);
                Ok(())
            }
            Expr::Await(node) => {
                let open = self.open(prec, Prec::Await);
                self.write("await ");
                self.expr(&node.value, Prec::Atom)?;
                self.close(open);
                Ok(())
            }
            Expr::Yield(node) => self.yield_value(node.value.as_deref(), prec),
            Expr::YieldFrom(node) => {
                let open = self.open(prec, Prec::Yield);
                self.write("yield from ");
                self.expr(&node.value, Prec::Atom)?;
                self.close(open);
                Ok(())
            }
            _ => self.primary(expr, prec),
        }
    }

    fn binary(&mut self, node: &ExprBinOp, prec: Prec) -> Result<(), Failure> {
        let text = operator(node.op).1;
        let own = binary_precedence(text);
        let (left, right) = if node.op == Operator::Pow {
            (own.next(), own)
        } else {
            (own, own.next())
        };
        let open = self.open(prec, own);
        self.expr(&node.left, left)?;
        self.write(&format!(" {text} "));
        self.expr(&node.right, right)?;
        self.close(open);
        Ok(())
    }

    fn compare(&mut self, node: &ExprCompare, prec: Prec) -> Result<(), Failure> {
        let Some((left, rest)) = node.operands.split_first() else {
            return Err(Failure::Invalid);
        };
        let open = self.open(prec, Prec::Cmp);
        self.expr(left, Prec::Expr)?;
        for (op, item) in node.ops.iter().zip(rest) {
            self.write(&format!(" {} ", cmp_op(*op).1));
            self.expr(item, Prec::Expr)?;
        }
        self.close(open);
        Ok(())
    }

    fn conditional(&mut self, node: &ExprIf, prec: Prec) -> Result<(), Failure> {
        let open = self.open(prec, Prec::Test);
        self.expr(&node.body, Prec::Or)?;
        self.write(" if ");
        self.expr(&node.test, Prec::Or)?;
        self.write(" else ");
        self.expr(&node.orelse, Prec::Test)?;
        self.close(open);
        Ok(())
    }

    fn lambda(&mut self, node: &ExprLambda, prec: Prec) -> Result<(), Failure> {
        let open = self.open(prec, Prec::Test);
        self.write("lambda");
        let mut inner = self.nested();
        if let Some(params) = &node.parameters {
            inner.arguments(params)?;
        }
        if !inner.out.is_empty() {
            self.write(" ");
            self.write(&inner.out);
        }
        self.write(": ");
        self.expr(&node.body, Prec::Test)?;
        self.close(open);
        Ok(())
    }

    fn yield_value(&mut self, value: Option<&Expr>, prec: Prec) -> Result<(), Failure> {
        let open = self.open(prec, Prec::Yield);
        self.write("yield");
        if let Some(value) = value {
            self.write(" ");
            self.expr(value, Prec::Atom)?;
        }
        self.close(open);
        Ok(())
    }

    /// A writer that shares the depth of this one and has its own text (`buffered`).
    fn nested(&self) -> Self {
        let mut writer = Writer::new(self.minor, self.source, self.avoid_backslashes);
        writer.depth = self.depth;
        writer
    }

    fn unary(&mut self, op: UnaryOp, operand: &Expr, prec: Prec) -> Result<(), Failure> {
        let text = unary_op(op).1;
        let own = if op == UnaryOp::Not {
            Prec::Not
        } else {
            Prec::Factor
        };
        let open = self.open(prec, own);
        self.write(text);
        self.expr(operand, own)?;
        self.close(open);
        Ok(())
    }

    /// `visit_BoolOp`: each value has a precedence one level higher than the value before it.
    fn bool_op(&mut self, op: BoolOp, values: &[Expr], prec: Prec) -> Result<(), Failure> {
        let text = format!(" {} ", bool_op(op).1);
        let own = if op == BoolOp::And {
            Prec::And
        } else {
            Prec::Or
        };
        let open = self.open(prec, own);
        let mut level = own;
        for (index, value) in values.iter().enumerate() {
            if index > 0 {
                self.write(&text);
            }
            level = level.next();
            self.expr(value, level)?;
        }
        self.close(open);
        Ok(())
    }

    fn primary(&mut self, expr: &Expr, prec: Prec) -> Result<(), Failure> {
        match expr {
            Expr::Attribute(node) => {
                self.expr(&node.value, Prec::Atom)?;
                // `3.__abs__()` is a syntax error: an `int` (or a `bool`) takes a space.
                let integer = match &*node.value {
                    Expr::NumberLiteral(number) => matches!(number.value, Number::Int(_)),
                    value => matches!(value, Expr::BooleanLiteral(_)),
                };
                self.write(if integer { " ." } else { "." });
                self.write(node.attr.as_str());
            }
            Expr::Call(node) => self.call(node)?,
            Expr::Subscript(node) => {
                self.expr(&node.value, Prec::Atom)?;
                self.write("[");
                match &*node.slice {
                    Expr::Tuple(tuple) if !tuple.elts.is_empty() => self.items_view(&tuple.elts)?,
                    slice => self.expr(slice, Prec::Test)?,
                }
                self.write("]");
            }
            Expr::Starred(node) => {
                self.write("*");
                self.expr(&node.value, Prec::Expr)?;
            }
            Expr::Slice(node) => self.slice_expr(node)?,
            _ => self.display(expr, prec)?,
        }
        Ok(())
    }

    fn call(&mut self, node: &ExprCall) -> Result<(), Failure> {
        self.expr(&node.func, Prec::Atom)?;
        self.write("(");
        let mut comma = false;
        for arg in &node.arguments.args {
            self.comma(&mut comma);
            self.expr(arg, Prec::Test)?;
        }
        for keyword in &node.arguments.keywords {
            self.comma(&mut comma);
            let name = keyword
                .arg
                .as_ref()
                .map(|name| format!("{}=", name.as_str()));
            self.write(name.as_deref().unwrap_or("**"));
            self.expr(&keyword.value, Prec::Test)?;
        }
        self.write(")");
        Ok(())
    }

    fn slice_expr(&mut self, node: &ExprSlice) -> Result<(), Failure> {
        if let Some(lower) = &node.lower {
            self.expr(lower, Prec::Test)?;
        }
        self.write(":");
        if let Some(upper) = &node.upper {
            self.expr(upper, Prec::Test)?;
        }
        if let Some(step) = &node.step {
            self.write(":");
            self.expr(step, Prec::Test)?;
        }
        Ok(())
    }

    fn comma(&mut self, comma: &mut bool) {
        if *comma {
            self.write(", ");
        }
        *comma = true;
    }

    /// The displays: list, tuple, set, dict and the comprehensions.
    fn display(&mut self, expr: &Expr, prec: Prec) -> Result<(), Failure> {
        match expr {
            Expr::List(node) => {
                self.write("[");
                self.items(&node.elts)?;
                self.write("]");
            }
            Expr::Tuple(node) => {
                let open = node.elts.is_empty() || prec > Prec::Tuple;
                self.write(if open { "(" } else { "" });
                self.items_view(&node.elts)?;
                self.write(if open { ")" } else { "" });
            }
            Expr::Set(node) if node.elts.is_empty() => self.write("{*()}"),
            Expr::Set(node) => {
                self.write("{");
                self.items(&node.elts)?;
                self.write("}");
            }
            Expr::Dict(node) => self.dict(node)?,
            Expr::ListComp(node) => self.comprehension("[", &node.elt, &node.generators, "]")?,
            Expr::SetComp(node) => self.comprehension("{", &node.elt, &node.generators, "}")?,
            Expr::Generator(node) => self.comprehension("(", &node.elt, &node.generators, ")")?,
            Expr::DictComp(node) => {
                let key = node.key.as_deref().ok_or(Failure::Invalid)?;
                self.write("{");
                self.expr(key, Prec::Test)?;
                self.write(": ");
                self.comprehension("", &node.value, &node.generators, "}")?;
            }
            _ => return Err(Failure::Invalid),
        }
        Ok(())
    }

    fn dict(&mut self, node: &ExprDict) -> Result<(), Failure> {
        self.write("{");
        for (index, item) in node.items.iter().enumerate() {
            if index > 0 {
                self.write(", ");
            }
            if let Some(key) = &item.key {
                self.expr(key, Prec::Test)?;
                self.write(": ");
                self.expr(&item.value, Prec::Test)?;
            } else {
                self.write("**");
                self.expr(&item.value, Prec::Expr)?;
            }
        }
        self.write("}");
        Ok(())
    }

    fn comprehension(
        &mut self,
        open: &str,
        elt: &Expr,
        generators: &[Comprehension],
        close: &str,
    ) -> Result<(), Failure> {
        self.write(open);
        self.expr(elt, Prec::Test)?;
        for generator in generators {
            self.write(if generator.is_async {
                " async for "
            } else {
                " for "
            });
            self.expr(&generator.target, Prec::Tuple)?;
            self.write(" in ");
            self.expr(&generator.iter, Prec::Or)?;
            for condition in &generator.ifs {
                self.write(" if ");
                self.expr(condition, Prec::Or)?;
            }
        }
        self.write(close);
        Ok(())
    }
}
