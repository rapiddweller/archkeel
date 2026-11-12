// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The string literals whose CPython value or tree native cannot write: each one gives a named
//! failure, never a text that differs (AD-377 points 14 to 16).

use ruff_python_ast::{
    Expr, FStringPartRef, InterpolatedStringElement, InterpolatedStringElements,
};
use ruff_text_size::{Ranged, TextRange};

use super::outcome::Failure;

/// The parser replaced a lone surrogate escape with U+FFFD: the value has U+FFFD and the source
/// of the literal has a backslash. A U+FFFD that the source spells gives the failure too.
pub fn replaced(value: &str, source: &str) -> bool {
    value.contains('\u{fffd}') && source.contains('\\')
}

/// A format spec nests at most this deep in the tree that CPython keeps.
const MAX_SPEC_DEPTH: u8 = 2;

struct Check<'s> {
    source: &'s str,
    minor: u32,
}

impl Check<'_> {
    fn slice(&self, range: TextRange) -> &str {
        self.source.get(range.to_std_range()).unwrap_or("")
    }

    fn elements(
        &self,
        elements: &InterpolatedStringElements,
        raw: bool,
        depth: u8,
    ) -> Option<Failure> {
        elements
            .iter()
            .find_map(|element| self.element(element, raw, depth))
    }

    fn element(
        &self,
        element: &InterpolatedStringElement,
        raw: bool,
        depth: u8,
    ) -> Option<Failure> {
        let field = match element {
            InterpolatedStringElement::Literal(literal) => {
                let source = self.slice(literal.range());
                return replaced(&literal.value, source).then_some(Failure::Unseen);
            }
            InterpolatedStringElement::Interpolation(field) => field,
        };
        let spec = field.format_spec.as_deref()?;
        if depth >= MAX_SPEC_DEPTH {
            return Some(Failure::SpecDepth);
        }
        // CPython 3.12 keeps `\N{...}` in a spec as a `Constant`, and it decodes the escapes of
        // the spec of a raw f-string (L-37a: a gap, not a port of the bug).
        let text = self.slice(spec.range());
        if self.minor == 12 && (text.contains("\\N{") || (raw && text.contains('\\'))) {
            return Some(Failure::Spec312);
        }
        self.elements(&spec.elements, raw, depth + 1)
    }
}

/// The failure of a string literal, an f-string or a t-string, or `None`. The fields of an
/// f-string are expressions of their own: a walk reaches them.
pub fn hazard(expr: &Expr, source: &str, minor: u32) -> Option<Failure> {
    let check = Check { source, minor };
    match expr {
        Expr::StringLiteral(node) => {
            replaced(node.value.to_str(), check.slice(node.range())).then_some(Failure::Unseen)
        }
        Expr::FString(node) => node.value.iter().find_map(|part| match part {
            FStringPartRef::Literal(literal) => {
                replaced(&literal.value, check.slice(literal.range())).then_some(Failure::Unseen)
            }
            FStringPartRef::FString(fstring) => {
                let raw = fstring.flags.prefix().is_raw();
                check.elements(&fstring.elements, raw, 0)
            }
        }),
        Expr::TString(node) => node.value.iter().find_map(|part| {
            let raw = part.flags.prefix().is_raw();
            check.elements(&part.elements, raw, 0)
        }),
        _ => None,
    }
}
