// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Simple statement text for attached type-ignore comments. Other statements refuse the file.

use ruff_python_ast::{Expr, Stmt};

use crate::bindings::scan::{Result, Scan};
use crate::module::Module;

fn expr(scan: &mut Scan, module: &Module, node: &Expr) -> Result<String> {
    super::super::class::text(scan, node, module.text())?
        .ok_or_else(|| "typing statement text unavailable".into())
}

pub(super) fn text(scan: &mut Scan, module: &Module, node: &Stmt) -> Result<String> {
    Ok(match node {
        Stmt::Expr(n) => expr(scan, module, &n.value)?,
        Stmt::Pass(_) => "pass".into(),
        Stmt::Break(_) => "break".into(),
        Stmt::Continue(_) => "continue".into(),
        Stmt::Return(n) => match &n.value {
            Some(n) => format!("return {}", expr(scan, module, n)?),
            None => "return".into(),
        },
        Stmt::Assign(n) => {
            let mut parts = Vec::new();
            for target in &n.targets {
                scan.tick(1)?;
                parts.push(expr(scan, module, target)?);
            }
            parts.push(expr(scan, module, &n.value)?);
            parts.join(" = ")
        }
        Stmt::AnnAssign(n) => {
            let target = expr(scan, module, &n.target)?;
            let target = if !n.simple && matches!(&*n.target, Expr::Name(_)) {
                format!("({target})")
            } else {
                target
            };
            let text = format!("{target}: {}", expr(scan, module, &n.annotation)?);
            suffix(scan, module, text, " = ", n.value.as_deref())?
        }
        Stmt::AugAssign(n) => format!(
            "{} {}= {}",
            expr(scan, module, &n.target)?,
            crate::pyast::operator(n.op).1,
            expr(scan, module, &n.value)?
        ),
        Stmt::Delete(n) => {
            let mut parts = Vec::new();
            for target in &n.targets {
                scan.tick(1)?;
                parts.push(expr(scan, module, target)?);
            }
            format!("del {}", parts.join(", "))
        }
        Stmt::Raise(n) => {
            let text = suffix(scan, module, "raise".into(), " ", n.exc.as_deref())?;
            suffix(scan, module, text, " from ", n.cause.as_deref())?
        }
        Stmt::Assert(n) => {
            let text = format!("assert {}", expr(scan, module, &n.test)?);
            suffix(scan, module, text, ", ", n.msg.as_deref())?
        }
        Stmt::Import(n) => format!("import {}", aliases(scan, &n.names)?),
        Stmt::ImportFrom(n) => {
            scan.tick(n.level as usize)?;
            format!(
                "from {}{} import {}",
                ".".repeat(n.level as usize),
                n.module.as_ref().map_or("", |m| m.as_str()),
                aliases(scan, &n.names)?
            )
        }
        Stmt::Global(n) => {
            scan.tick(n.names.len())?;
            format!(
                "global {}",
                n.names
                    .iter()
                    .map(|n| n.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        Stmt::Nonlocal(n) => {
            scan.tick(n.names.len())?;
            format!(
                "nonlocal {}",
                n.names
                    .iter()
                    .map(|n| n.as_str())
                    .collect::<Vec<_>>()
                    .join(", ")
            )
        }
        _ => return Err("typing attached compound statement text not ported".into()),
    })
}

fn suffix(
    scan: &mut Scan,
    module: &Module,
    mut text: String,
    separator: &str,
    value: Option<&Expr>,
) -> Result<String> {
    if let Some(value) = value {
        text.push_str(separator);
        text.push_str(&expr(scan, module, value)?);
    }
    Ok(text)
}

fn aliases(scan: &mut Scan, aliases: &[ruff_python_ast::Alias]) -> Result<String> {
    let mut parts = Vec::new();
    for a in aliases {
        scan.tick(1usize.saturating_add(a.name.len()))?;
        parts.push(match &a.asname {
            Some(n) => format!("{} as {n}", a.name),
            None => a.name.to_string(),
        });
    }
    Ok(parts.join(", "))
}
