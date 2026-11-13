// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Literal admission follows ast.literal_eval, including unhashable set and dict keys.

use super::scan::{constant, Result, Scan};
use crate::pyast::Node;
use ruff_python_ast::{Expr, Number, Operator, UnaryOp};

pub(in crate::bindings) fn inert(scan: &mut Scan, node: &Expr, depth: usize) -> Result<bool> {
    if depth >= 100 {
        return Err("creation operand depth limit exceeded (100 levels)".into());
    }
    if let Expr::Lambda(n) = node {
        for parameter in n
            .parameters
            .iter()
            .flat_map(|p| p.posonlyargs.iter().chain(&p.args).chain(&p.kwonlyargs))
        {
            scan.tick(1)?;
            let Some(default) = parameter.default.as_deref() else {
                continue;
            };
            if !inert(scan, default, depth + 1)? {
                return Ok(false);
            }
        }
        return Ok(true);
    }
    let node = match node {
        Expr::Named(n) if matches!(&*n.target, Expr::Name(_)) => &*n.value,
        n => n,
    };
    for node in scan.walk(Node::Expr(node))? {
        scan.tick(1)?;
        if matches!(node, Node::Expr(Expr::Call(_))) {
            return Ok(false);
        }
    }
    Ok(literal(scan, node, depth)?.is_some())
}

// Some(hashable) is a valid literal. None means literal_eval raises an exception.
fn literal(scan: &mut Scan, node: &Expr, depth: usize) -> Result<Option<bool>> {
    scan.tick(1)?;
    if depth >= 100 {
        return Err("creation operand depth limit exceeded (100 levels)".into());
    }
    if constant(node) {
        return Ok(Some(true));
    }
    let (items, hashable, require_hashable) = match node {
        Expr::Tuple(n) => (&n.elts, true, false),
        Expr::List(n) => (&n.elts, false, false),
        Expr::Set(n) => (&n.elts, false, true),
        Expr::Dict(n) => {
            for item in &n.items {
                scan.tick(1)?;
                let Some(key) = item.key.as_ref() else {
                    return Ok(None);
                };
                if literal(scan, key, depth + 1)? != Some(true)
                    || literal(scan, &item.value, depth + 1)?.is_none()
                {
                    return Ok(None);
                }
            }
            return Ok(Some(false));
        }
        Expr::UnaryOp(n) if matches!(n.op, UnaryOp::UAdd | UnaryOp::USub) => {
            return Ok(matches!(&*n.operand, Expr::NumberLiteral(_)).then_some(true));
        }
        Expr::BinOp(n) if matches!(n.op, Operator::Add | Operator::Sub) => {
            let left = match &*n.left {
                Expr::UnaryOp(n) if matches!(n.op, UnaryOp::UAdd | UnaryOp::USub) => &*n.operand,
                n => n,
            };
            return Ok((matches!(left, Expr::NumberLiteral(n) if matches!(n.value, Number::Int(_) | Number::Float(_)))
                && matches!(&*n.right, Expr::NumberLiteral(n) if matches!(n.value, Number::Complex { .. }))).then_some(true));
        }
        _ => return Ok(None),
    };
    let mut all_hashable = hashable;
    for item in items {
        scan.tick(1)?;
        let Some(child_hashable) = literal(scan, item, depth + 1)? else {
            return Ok(None);
        };
        if require_hashable && !child_hashable {
            return Ok(None);
        }
        all_hashable &= child_hashable;
    }
    Ok(Some(all_hashable))
}

#[cfg(test)]
mod tests {
    #[test]
    fn literal_admission_stops_at_its_named_depth_bound() {
        let tree = crate::test_tree("x = 1\n", 11).expect("fixture");
        let node = tree
            .body
            .first()
            .and_then(|stmt| match stmt {
                ruff_python_ast::Stmt::Assign(n) => Some(n),
                _ => None,
            })
            .expect("fixture assignment");
        let mut scan = super::Scan::new(crate::test_minor(11));
        assert_eq!(
            super::inert(&mut scan, &node.value, 100),
            Err("creation operand depth limit exceeded (100 levels)".into())
        );
    }
}
