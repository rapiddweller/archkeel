// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Named Unicode escapes must use the database of the request's CPython minor.

use super::work::Work;
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{
    Expr, FStringPartRef, InterpolatedStringElement, InterpolatedStringElements,
};
use ruff_text_size::Ranged;
use std::sync::OnceLock;

type Ranges = Vec<(u32, u32)>;
const TABLE: &str = include_str!("unassigned.txt");

fn unassigned(c: char, minor: PyMinor) -> bool {
    static TABLES: OnceLock<[Ranges; 4]> = OnceLock::new();
    let tables = TABLES.get_or_init(|| {
        std::array::from_fn(|index| {
            TABLE
                .lines()
                .nth(index)
                .into_iter()
                .flat_map(str::split_whitespace)
                .filter_map(|range| {
                    let (low, high) = range.split_once('-')?;
                    Some((
                        u32::from_str_radix(low, 16).ok()?,
                        u32::from_str_radix(high, 16).ok()?,
                    ))
                })
                .collect()
        })
    });
    let ranges = match minor {
        PyMinor::Py311 => &tables[0],
        PyMinor::Py312 => &tables[1],
        PyMinor::Py313 => &tables[2],
        PyMinor::Py314 => &tables[3],
    };
    let code = u32::from(c);
    ranges
        .binary_search_by(|&(low, high)| {
            if high < code {
                std::cmp::Ordering::Less
            } else if low > code {
                std::cmp::Ordering::Greater
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

fn literal(
    value: &str,
    source: &str,
    minor: PyMinor,
    work: &mut Work,
    docstring: bool,
) -> Option<&'static str> {
    if !work.charge(source.len().saturating_add(value.len())) {
        return Some("CPython validation work limit exceeded");
    }
    let surrogates = match minor {
        PyMinor::Py311 | PyMinor::Py312 => false,
        PyMinor::Py313 | PyMinor::Py314 => docstring,
    };
    if !source.contains("\\N{") && !surrogates {
        return None;
    }
    if source.contains("\\N{") && value.chars().any(|c| unassigned(c, minor)) {
        return Some("named Unicode escape is not assigned in this CPython version");
    }
    let legacy = match minor {
        PyMinor::Py311 | PyMinor::Py312 => true,
        PyMinor::Py313 | PyMinor::Py314 => false,
    };
    let mut chars = source.chars();
    while let Some(c) = chars.next() {
        if !work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        if c != '\\' {
            continue;
        }
        let escape = chars.next();
        if surrogates && matches!(escape, Some('u' | 'U')) {
            let code = escape_code(&mut chars, if escape == Some('u') { 4 } else { 8 }, work)?;
            if (0xd800..=0xdfff).contains(&code) {
                return Some("CPython cannot encode a surrogate string constant");
            }
            continue;
        }
        if escape != Some('N') || chars.next() != Some('{') {
            continue;
        }
        let mut name = String::new();
        for c in chars.by_ref() {
            if !work.charge(1) {
                return Some("CPython validation work limit exceeded");
            }
            if c == '}' {
                break;
            }
            name.push(c);
        }
        if let Some(reason) = named_escape(&name, legacy) {
            return Some(reason);
        }
    }
    None
}

fn escape_code(chars: &mut std::str::Chars<'_>, digits: usize, work: &mut Work) -> Option<u32> {
    let mut code = 0u32;
    for _ in 0..digits {
        if !work.charge(1) {
            return None;
        }
        code = code
            .saturating_mul(16)
            .saturating_add(chars.next()?.to_digit(16)?);
    }
    Some(code)
}

fn named_escape(name: &str, legacy: bool) -> Option<&'static str> {
    let upper = name.to_ascii_uppercase();
    if legacy && upper.starts_with("HANGUL SYLLABLE ") && name != upper {
        return Some("lowercase Hangul syllable name is not accepted by this CPython version");
    }
    let hex = upper.strip_prefix("CJK UNIFIED IDEOGRAPH-")?;
    if legacy && name != upper {
        return Some("lowercase CJK name is not accepted by this CPython version");
    }
    if !legacy
        && u32::from_str_radix(hex, 16)
            .ok()
            .is_none_or(|code| format!("{code:04X}") != hex)
    {
        return Some("non-canonical CJK named Unicode escape");
    }
    None
}

struct Check<'a> {
    source: &'a str,
    minor: PyMinor,
    work: &'a mut Work,
    docstring: bool,
}
impl Check<'_> {
    fn text(&self, node: &impl Ranged) -> &str {
        self.source.get(node.range().to_std_range()).unwrap_or("")
    }

    fn elements(
        &mut self,
        elements: &InterpolatedStringElements,
        raw: bool,
        depth: usize,
    ) -> Option<&'static str> {
        if depth > 2 {
            return Some("f-string expressions nested too deeply");
        }
        for element in elements.iter() {
            if !self.work.charge(1) {
                return Some("CPython validation work limit exceeded");
            }
            if let Some(reason) = self.element(element, raw, depth) {
                return Some(reason);
            }
        }
        None
    }

    fn element(
        &mut self,
        element: &InterpolatedStringElement,
        raw: bool,
        depth: usize,
    ) -> Option<&'static str> {
        let node = match element {
            InterpolatedStringElement::Literal(node) if !raw => {
                let text = self.text(node).to_owned();
                return literal(&node.value, &text, self.minor, self.work, false);
            }
            InterpolatedStringElement::Literal(_) => return None,
            InterpolatedStringElement::Interpolation(node) => node,
        };
        let spec = node.format_spec.as_deref()?;
        let text = self.text(spec).to_owned();
        if !self.work.charge(text.len()) {
            return Some("CPython validation work limit exceeded");
        }
        let broken = match self.minor {
            PyMinor::Py312 => raw && raw_spec_failure(&text),
            PyMinor::Py311 | PyMinor::Py313 | PyMinor::Py314 => false,
        };
        if broken {
            return Some("CPython 3.12 cannot decode this raw format spec escape");
        }
        self.elements(&spec.elements, raw, depth + 1)
    }

    fn literal_part(&mut self, part: &ruff_python_ast::StringLiteral) -> Option<&'static str> {
        if !self.work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        if part.flags.prefix().is_raw() {
            return None;
        }
        let text = self.text(part).to_owned();
        literal(&part.value, &text, self.minor, self.work, self.docstring)
    }

    fn fstring_part(&mut self, part: FStringPartRef<'_>) -> Option<&'static str> {
        if !self.work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        match part {
            FStringPartRef::FString(part) => {
                self.elements(&part.elements, part.flags.prefix().is_raw(), 0)
            }
            FStringPartRef::Literal(part) => self.literal_part(part),
        }
    }
}

fn raw_spec_failure(text: &str) -> bool {
    let mut chars = text.chars();
    while let Some(c) = chars.next() {
        if c != '\\' {
            continue;
        }
        let Some(escape) = chars.next() else {
            return true;
        };
        if escape == 'N' {
            return true;
        }
        let digits = match escape {
            'x' => 2,
            'u' => 4,
            'U' => 8,
            _ => continue,
        };
        let mut value = 0u32;
        for _ in 0..digits {
            let Some(digit) = chars.next().and_then(|c| c.to_digit(16)) else {
                return true;
            };
            value = value * 16 + digit;
        }
        if value > 0x10ffff {
            return true;
        }
    }
    false
}

pub fn check(expr: &Expr, source: &str, minor: PyMinor, work: &mut Work) -> Option<&'static str> {
    let mut check = Check {
        source,
        minor,
        work,
        docstring: false,
    };
    match expr {
        Expr::StringLiteral(node) => node.value.iter().find_map(|part| check.literal_part(part)),
        Expr::FString(node) => node.value.iter().find_map(|part| check.fstring_part(part)),
        Expr::TString(node) => {
            for part in node.value.iter() {
                if !check.work.charge(1) {
                    return Some("CPython validation work limit exceeded");
                }
                if let Some(reason) =
                    check.elements(&part.elements, part.flags.prefix().is_raw(), 0)
                {
                    return Some(reason);
                }
            }
            None
        }
        _ => None,
    }
}

pub fn docstring(
    body: &[ruff_python_ast::Stmt],
    source: &str,
    minor: PyMinor,
    work: &mut Work,
) -> Option<&'static str> {
    let ruff_python_ast::Stmt::Expr(stmt) = body.first()? else {
        return None;
    };
    let Expr::StringLiteral(node) = &*stmt.value else {
        return None;
    };
    let mut check = Check {
        source,
        minor,
        work,
        docstring: true,
    };
    node.value.iter().find_map(|part| check.literal_part(part))
}
