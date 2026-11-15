// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Generic parameters that can hide the first name of an expression path.

use std::collections::BTreeSet;

use syn::visit::{self, Visit};
use syn::{ExprPath, GenericParam};

use crate::tokens::plain;

pub(super) fn generic_paths(file: &syn::File) -> BTreeSet<(i64, i64)> {
    let mut found = Names::default();
    found.visit_file(file);
    found
        .paths
        .into_iter()
        .filter(|(_, name)| found.generics.contains(name))
        .map(|(site, _)| site)
        .collect()
}

#[derive(Default)]
struct Names {
    generics: BTreeSet<String>,
    paths: Vec<((i64, i64), String)>,
}

impl<'ast> Visit<'ast> for Names {
    fn visit_generic_param(&mut self, node: &'ast GenericParam) {
        let name = match node {
            GenericParam::Type(value) => Some(&value.ident),
            GenericParam::Const(value) => Some(&value.ident),
            GenericParam::Lifetime(_) => None,
        };
        if let Some(name) = name {
            self.generics.insert(plain(name));
        }
        visit::visit_generic_param(self, node);
    }

    fn visit_expr_path(&mut self, node: &'ast ExprPath) {
        if node.qself.is_none() && node.path.leading_colon.is_none() && node.path.segments.len() > 1 {
            if let Some(first) = node.path.segments.first() {
                let start = first.ident.span().start();
                let line = i64::try_from(start.line).unwrap_or(i64::MAX);
                let column = i64::try_from(start.column).unwrap_or(i64::MAX);
                self.paths.push(((line, column), plain(&first.ident)));
            }
        }
        visit::visit_expr_path(self, node);
    }
}
