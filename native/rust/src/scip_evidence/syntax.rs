// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Map verified Rust call and declaration tokens to exact AST identities.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::identity::{evidence_id, stable_id, Part};
use proc_macro2::Span;
use scip_serde::{Deserialize, Serialize};
use syn::visit::{self, Visit};

use super::wire::Range;
type Result<T> = std::result::Result<T, String>;

#[derive(Deserialize)]
#[serde(crate = "scip_serde", deny_unknown_fields)]
pub(super) struct CallSite {
    pub id: String,
    pub path: String,
    pub line: usize,
    pub module: String,
    pub expression: String,
    #[serde(default)]
    pub macro_call: bool,
}

#[derive(Clone, Copy, Eq, PartialEq, Serialize)]
#[serde(crate = "scip_serde", rename_all = "snake_case")]
pub(super) enum Dispatch {
    Direct,
    TraitDispatch,
}

pub(super) struct Source<'a> {
    pub calls: BTreeMap<Range, BTreeSet<&'a str>>,
    pub definitions: BTreeMap<Range, (&'a str, String, Dispatch)>,
}

pub(super) fn source<'a>(
    path: &str,
    text: &str,
    rows: Option<&'a BTreeMap<usize, Vec<CallSite>>>,
    ids: &'a BTreeMap<String, Option<String>>,
) -> Result<Source<'a>> {
    let mut reader = Reader {
        path,
        lines: text.lines().collect(),
        rows,
        ids,
        trait_impl: false,
        data: Source {
            calls: BTreeMap::new(),
            definitions: BTreeMap::new(),
        },
    };
    let file = syn::parse_file(text).map_err(|error| format!("{path}: {error}"))?;
    reader.visit_file(&file);
    Ok(reader.data)
}

struct Reader<'a, 'b> {
    path: &'b str,
    lines: Vec<&'b str>,
    rows: Option<&'a BTreeMap<usize, Vec<CallSite>>>,
    ids: &'a BTreeMap<String, Option<String>>,
    data: Source<'a>,
    trait_impl: bool,
}

fn number(n: usize) -> i64 {
    i64::try_from(n).unwrap_or(i64::MAX)
}

fn plain(id: &syn::Ident) -> String {
    id.to_string().trim_start_matches("r#").to_owned()
}

impl Reader<'_, '_> {
    fn byte_column(&self, line: usize, column: usize) -> Option<u32> {
        let text = *self.lines.get(line.checked_sub(1)?)?;
        let bytes = text.chars().take(column).map(char::len_utf8).sum::<usize>();
        u32::try_from(bytes).ok()
    }

    fn range(&self, span: Span) -> Option<Range> {
        let (s, e) = (span.start(), span.end());
        Some(Range([
            u32::try_from(s.line.checked_sub(1)?).ok()?,
            self.byte_column(s.line, s.column)?,
            u32::try_from(e.line.checked_sub(1)?).ok()?,
            self.byte_column(e.line, e.column)?,
        ]))
    }

    fn declaration(&mut self, name: &syn::Ident, dispatch: Dispatch) {
        let span = name.span();
        let s = span.start();
        let evidence = evidence_id(
            self.path,
            number(s.line),
            number(span.end().line),
            number(s.column),
        );
        if let (Some(range), Some(Some(id))) = (self.range(span), self.ids.get(&evidence)) {
            self.data
                .definitions
                .insert(range, (id, evidence, dispatch));
        }
    }

    fn call(&mut self, span: Span, token: Span, expression: &str) {
        let (s, e) = (span.start(), span.end());
        let Some(rows) = self.rows.and_then(|rows| rows.get(&s.line)) else {
            return;
        };
        let Some(range) = self.range(token) else {
            return;
        };
        for row in rows {
            if row.expression != expression {
                continue;
            }
            let identity = stable_id(
                "RSCALL",
                &[
                    Part::Text(&row.module),
                    Part::Text(self.path),
                    Part::Number(number(s.line)),
                    Part::Number(number(s.column)),
                    Part::Number(number(e.line)),
                    Part::Number(number(e.column)),
                ],
            );
            if row.id == identity {
                self.data.calls.entry(range).or_default().insert(&row.id);
            }
        }
    }
}

impl<'ast> Visit<'ast> for Reader<'_, '_> {
    fn visit_item_fn(&mut self, function: &'ast syn::ItemFn) {
        self.declaration(&function.sig.ident, Dispatch::Direct);
        visit::visit_item_fn(self, function);
    }

    fn visit_impl_item_fn(&mut self, method: &'ast syn::ImplItemFn) {
        let dispatch = if self.trait_impl {
            Dispatch::TraitDispatch
        } else {
            Dispatch::Direct
        };
        self.declaration(&method.sig.ident, dispatch);
        visit::visit_impl_item_fn(self, method);
    }

    fn visit_trait_item_fn(&mut self, method: &'ast syn::TraitItemFn) {
        self.declaration(&method.sig.ident, Dispatch::TraitDispatch);
        visit::visit_trait_item_fn(self, method);
    }

    fn visit_item_impl(&mut self, implementation: &'ast syn::ItemImpl) {
        let prior = self.trait_impl;
        self.trait_impl = implementation.trait_.is_some();
        visit::visit_item_impl(self, implementation);
        self.trait_impl = prior;
    }

    fn visit_expr_call(&mut self, call: &'ast syn::ExprCall) {
        if let Some((token, expression)) = function_token(&call.func) {
            self.call(call.paren_token.span.join(), token, &expression);
        }
        visit::visit_expr_call(self, call);
    }

    fn visit_expr_method_call(&mut self, call: &'ast syn::ExprMethodCall) {
        self.call(call.method.span(), call.method.span(), &plain(&call.method));
        visit::visit_expr_method_call(self, call);
    }
}

fn function_token(recv: &syn::Expr) -> Option<(Span, String)> {
    let syn::Expr::Path(path) = recv else {
        return None;
    };
    let token = path.path.segments.last()?.ident.span();
    let ordinary = path.qself.is_none()
        && path.path.leading_colon.is_none()
        && path
            .path
            .segments
            .iter()
            .all(|seg| matches!(seg.arguments, syn::PathArguments::None));
    let expression = if ordinary {
        path.path
            .segments
            .iter()
            .map(|s| plain(&s.ident))
            .collect::<Vec<_>>()
            .join("::")
    } else {
        "<call>".to_owned()
    };
    Some((token, expression))
}
