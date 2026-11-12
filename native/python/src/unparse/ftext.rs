// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `visit_JoinedStr` and `visit_TemplateStr`: an f-string or a t-string from its CPython values.
//!
//! 3.12 to 3.14 escape the text parts and pick quotes that the field parts do not use. 3.11 escapes
//! each part with `_str_literal_helper`, and its fields avoid backslashes: a backslash in the text
//! of a field raises `ValueError`.

use crate::pyast::{fstring, Piece};

use super::literal::{self, ALL_QUOTES, MULTI_QUOTES};
use super::outcome::{Prec, TextFailure as Failure};
use super::{legacy, Writer};

/// The quotes that a field part leaves: a newline needs triple quotes, and a quote that the field
/// uses is out unless no quote is left.
fn field_quotes(value: &str, mut quotes: Vec<&'static str>) -> Vec<&'static str> {
    if value.contains('\n') {
        quotes.retain(|quote| MULTI_QUOTES.contains(quote));
    }
    let new: Vec<&'static str> = quotes
        .iter()
        .copied()
        .filter(|quote| !value.contains(quote))
        .collect();
    if new.is_empty() {
        quotes
    } else {
        new
    }
}

impl Writer<'_> {
    pub(super) fn ftext(&mut self, pieces: &[Piece<'_>], prefix: &str) -> Result<(), Failure> {
        self.write(prefix);
        let mut parts: Vec<(String, bool)> = Vec::with_capacity(pieces.len());
        for piece in pieces {
            let mut buffer = String::new();
            self.inner_piece(piece, false, &mut buffer)?;
            parts.push((buffer, matches!(piece, Piece::Text(_))));
        }
        if legacy(self.minor) && self.avoid_backslashes {
            let joined: String = parts.into_iter().map(|(text, _)| text).collect();
            let text = literal::avoiding_backslashes(&joined, &ALL_QUOTES, self.minor);
            self.write(&text);
            return Ok(());
        }
        let text = self.quoted(&parts);
        self.write(&text);
        Ok(())
    }

    /// `_write_fstring_inner` of one value.
    fn inner_piece(&self, piece: &Piece<'_>, spec: bool, out: &mut String) -> Result<(), Failure> {
        match piece {
            Piece::Text(text) => {
                out.push_str(&self.text_piece(text, spec));
                Ok(())
            }
            Piece::Value {
                expr,
                conversion,
                spec: format_spec,
                template,
            } => {
                let text = match template {
                    Some(field) => fstring::interpolation_text(field, self.source).to_owned(),
                    None => {
                        let mut writer = self.inner();
                        writer.expr(expr, Prec::Or)?;
                        writer.out
                    }
                };
                if legacy(self.minor) && text.contains('\\') {
                    return Err(Failure::Invalid);
                }
                out.push('{');
                out.push_str(if text.starts_with('{') { " " } else { "" });
                out.push_str(&text);
                let code = match conversion {
                    ruff_python_ast::ConversionFlag::None => None,
                    ruff_python_ast::ConversionFlag::Str => Some('s'),
                    ruff_python_ast::ConversionFlag::Repr => Some('r'),
                    ruff_python_ast::ConversionFlag::Ascii => Some('a'),
                };
                if let Some(code) = code {
                    out.push('!');
                    out.push(code);
                }
                if let Some(format_spec) = format_spec {
                    out.push(':');
                    self.spec_pieces(format_spec, out)?;
                }
                out.push('}');
                Ok(())
            }
        }
    }

    fn spec_pieces(&self, pieces: &[Piece<'_>], out: &mut String) -> Result<(), Failure> {
        for piece in pieces {
            self.inner_piece(piece, true, out)?;
        }
        Ok(())
    }

    /// A text part: braces doubled, and from 3.12 on the escapes of a format spec.
    fn text_piece(&self, text: &str, spec: bool) -> String {
        let text = text.replace('{', "{{").replace('}', "}}");
        if spec && !legacy(self.minor) {
            text.replace('\\', "\\\\")
                .replace('\'', "\\'")
                .replace('"', "\\\"")
                .replace('\n', "\\n")
        } else {
            text
        }
    }

    /// `_ftstring_helper` of 3.12 to 3.14, and the loop of 3.11, where each part (a field too)
    /// goes through `_str_literal_helper`.
    fn quoted(&self, parts: &[(String, bool)]) -> String {
        let modern = !legacy(self.minor);
        let mut quotes: Vec<&'static str> = ALL_QUOTES.to_vec();
        let mut written: Vec<String> = Vec::with_capacity(parts.len());
        for (value, constant) in parts {
            let next = if modern && !*constant {
                Some((value.clone(), field_quotes(value, quotes.clone())))
            } else {
                self.text_quotes(value, &quotes, *constant)
            };
            let Some((text, new)) = next else {
                return self.fallback(parts, modern);
            };
            quotes = new;
            written.push(text);
        }
        let quote = quotes.first().copied().unwrap_or("'");
        format!("{quote}{}{quote}", written.concat())
    }

    /// The escaped part and its quotes, or `None` when no quote of the parts before fits.
    fn text_quotes(
        &self,
        value: &str,
        quotes: &[&'static str],
        escape_special_whitespace: bool,
    ) -> Option<(String, Vec<&'static str>)> {
        let literal::Quotes { text, quotes: new } =
            literal::literal_helper(value, quotes, escape_special_whitespace, self.minor);
        let fits = new.iter().any(|quote| quotes.contains(quote));
        fits.then_some((text, new))
    }

    /// No quote fits each part: `repr` of each part in triple single quotes. From 3.12 on only the
    /// text parts go through `repr`.
    fn fallback(&self, parts: &[(String, bool)], only_text: bool) -> String {
        let mut text = String::new();
        for (value, constant) in parts {
            if *constant || !only_text {
                let repr = literal::repr_str(&format!("\"{value}"), self.minor);
                text.push_str(
                    repr.get(2..repr.len().saturating_sub(1))
                        .unwrap_or_default(),
                );
            } else {
                text.push_str(value);
            }
        }
        format!("'''{text}'''")
    }
}
