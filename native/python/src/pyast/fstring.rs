// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The `values` of a CPython `JoinedStr` or `TemplateStr` from the parts of a ruff f-string or
//! t-string.
//!
//! CPython joins the text of adjacent literal parts into one `Constant` and drops empty text. The
//! text of a debug field (`{x=}`) is a `Constant` too, and its value has the conversion `r` when
//! it has no conversion and no format spec. A format spec is a `JoinedStr` of its own.

use std::rc::Rc;

use ruff_python_ast::{
    ConversionFlag, Expr, FStringPartRef, FStringValue, InterpolatedElement,
    InterpolatedStringElement, InterpolatedStringElements, TStringValue,
};
use ruff_text_size::Ranged;

/// One value of a `JoinedStr` or a `TemplateStr`.
pub enum Piece<'a> {
    /// A `Constant` with a `str` value.
    Text(String),
    /// A `FormattedValue` (or an `Interpolation` of a t-string).
    Value {
        expr: &'a Expr,
        /// `-1`, or the code point of `s`, `r` or `a`.
        conversion: i32,
        spec: Option<Rc<[Piece<'a>]>>,
        /// The field of an `Interpolation` of a t-string: its `str` is source text.
        template: Option<&'a InterpolatedElement>,
    },
}

impl Piece<'_> {
    pub fn kind(&self) -> &'static str {
        match self {
            Piece::Text(_) => "Constant",
            Piece::Value {
                template: Some(_), ..
            } => "Interpolation",
            Piece::Value { .. } => "FormattedValue",
        }
    }
}

/// The values of an f-string, with its implicitly joined literal parts.
pub fn fstring(value: &FStringValue) -> Rc<[Piece<'_>]> {
    let mut out = Vec::new();
    for part in value.iter() {
        match part {
            FStringPartRef::Literal(literal) => push_text(&mut out, &literal.value),
            FStringPartRef::FString(fstring) => elements(&mut out, &fstring.elements, false),
        }
    }
    Rc::from(out)
}

/// The values of a t-string (3.14).
pub fn tstring(value: &TStringValue) -> Rc<[Piece<'_>]> {
    let mut out = Vec::new();
    for part in value.iter() {
        elements(&mut out, &part.elements, true);
    }
    Rc::from(out)
}

fn elements<'a>(
    out: &mut Vec<Piece<'a>>,
    elements: &'a InterpolatedStringElements,
    template: bool,
) {
    for element in elements.iter() {
        element_into(out, element, template, 0);
    }
}

/// A deeper spec is not kept: `unparse::string_failure` gives `SpecDepth`, a named gap, for it.
const MAX_SPEC_DEPTH: u8 = 2;

fn element_into<'a>(
    out: &mut Vec<Piece<'a>>,
    element: &'a InterpolatedStringElement,
    template: bool,
    depth: u8,
) {
    let field = match element {
        InterpolatedStringElement::Literal(literal) => return push_text(out, &literal.value),
        InterpolatedStringElement::Interpolation(field) => field,
    };
    if let Some(debug) = &field.debug_text {
        push_text(out, debug.as_str());
    }
    let spec = field
        .format_spec
        .as_ref()
        .filter(|_| depth < MAX_SPEC_DEPTH)
        .map(|spec| {
            let mut pieces = Vec::new();
            // A field in a format spec is a `FormattedValue`, also in a t-string.
            for element in spec.elements.iter() {
                element_into(&mut pieces, element, false, depth + 1);
            }
            Rc::from(pieces)
        });
    let mut conversion = code(field.conversion);
    if field.debug_text.is_some() && conversion == -1 && field.format_spec.is_none() {
        conversion = i32::from(b'r');
    }
    out.push(Piece::Value {
        expr: &field.expression,
        conversion,
        spec,
        template: template.then_some(field),
    });
}

/// `Interpolation.str`: the source from after `{` to the last token of the expression, with
/// its closing parentheses and without a comment or the white space after it.
pub fn interpolation_text<'s>(field: &InterpolatedElement, source: &'s str) -> &'s str {
    let start = field.start().to_usize() + 1;
    let mut end = field.expression.end().to_usize();
    let mut at = end;
    let bytes = source.as_bytes();
    while let Some(&byte) = bytes.get(at) {
        match byte {
            b')' => {
                at += 1;
                end = at;
            }
            // A line join ends the text: CPython keeps its backslash (`'a \\'`).
            b'\\' => {
                at += 1;
                end = at;
            }
            b' ' | b'\t' | b'\n' | b'\r' | b'\x0c' => at += 1,
            b'#' => {
                while bytes.get(at).is_some_and(|byte| *byte != b'\n') {
                    at += 1;
                }
            }
            _ => break,
        }
    }
    source.get(start..end).unwrap_or("")
}

fn code(flag: ConversionFlag) -> i32 {
    match flag {
        ConversionFlag::None => -1,
        ConversionFlag::Str => i32::from(b's'),
        ConversionFlag::Ascii => i32::from(b'a'),
        ConversionFlag::Repr => i32::from(b'r'),
    }
}

fn push_text(out: &mut Vec<Piece<'_>>, text: &str) {
    if text.is_empty() {
        return;
    }
    if let Some(Piece::Text(last)) = out.last_mut() {
        last.push_str(text);
    } else {
        out.push(Piece::Text(text.to_owned()));
    }
}
