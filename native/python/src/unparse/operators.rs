// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compound expressions of `_Unparser`, and `_Precedence`.
//!
//! A parent sets the precedence of a child before it writes it; a child that no parent set has
//! `TEST`. A node writes parentheses when its precedence is higher than the precedence that its
//! own operator needs (`require_parens`).

use ruff_python_ast::{
    BoolOp, Comprehension, Expr, ExprBinOp, ExprCall, ExprCompare, ExprDict, ExprIf, ExprLambda,
    ExprSlice, Number, Operator, UnaryOp,
};

use crate::pyast::{bool_op, cmp_op, operator, unary_op};

use super::outcome::{Failure, Prec};
use super::Writer;

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
