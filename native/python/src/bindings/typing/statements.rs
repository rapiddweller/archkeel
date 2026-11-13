// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Simple statement text for attached type-ignore comments. Other statements refuse the file.

use super::*;

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
            let mut text = format!("{target}: {}", expr(scan, module, &n.annotation)?);
            if let Some(value) = &n.value {
                text.push_str(&format!(" = {}", expr(scan, module, value)?));
            }
            text
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
            let mut text = "raise".to_owned();
            if let Some(e) = &n.exc {
                text.push_str(&format!(" {}", expr(scan, module, e)?));
            }
            if let Some(cause) = &n.cause {
                text.push_str(&format!(" from {}", expr(scan, module, cause)?));
            }
            text
        }
        Stmt::Assert(n) => {
            let mut text = format!("assert {}", expr(scan, module, &n.test)?);
            if let Some(msg) = &n.msg {
                text.push_str(&format!(", {}", expr(scan, module, msg)?));
            }
            text
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
