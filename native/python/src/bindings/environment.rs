// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Shared import-local lookup inputs, below their proof consumers.

use super::scan::{Result, Scan};
use super::{class, names, namespace};
use crate::module::Module;
use ruff_python_ast::{Expr, Stmt};
use std::collections::{BTreeSet, HashSet};

pub(super) struct Env<'a> {
    pub module: &'a Module,
    pub stable: BTreeSet<String>,
    pub unique: BTreeSet<String>,
    pub bound: HashSet<String>,
    pub opaque: bool,
}

impl Env<'_> {
    pub fn may_exist(
        &self,
        scan: &mut Scan,
        body: &[Stmt],
        stop: Option<&Stmt>,
        name: &str,
    ) -> Result<bool> {
        if !self.opaque && !self.bound.contains(name) {
            return Ok(false);
        }
        names::may_exist(scan, body, stop, name)
    }
}

pub(super) fn resolve(scan: &mut Scan, module: &Module, expr: &Expr) -> Result<String> {
    if let Some(text) = namespace::dotted(scan, expr)? {
        return Ok(text);
    }
    let text = class::text(scan, expr, module.text())?.unwrap_or_default();
    let (root, tail) = text
        .split_once('.')
        .map_or((text.as_str(), None), |(a, b)| (a, Some(b)));
    if let Some((target, _)) = scan.aliases.get(root) {
        let text = tail.map_or_else(|| target.to_owned(), |tail| format!("{target}.{tail}"));
        scan.tick(text.len())?;
        return Ok(text);
    }
    Ok(text)
}
