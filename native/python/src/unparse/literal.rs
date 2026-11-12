// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The literal texts of `ast.unparse`: `repr` of a `str`, `bytes`, `int`, `float` and `complex`,
//! and `_str_literal_helper`, which picks the quotes of a string with the fewest escapes.

use archkeel_facts::pyminor::PyMinor;
pub use archkeel_facts::pyrepr::printable;

/// `sys.get_int_max_str_digits()` of an isolated interpreter: `repr` of a longer `int` raises.
const MAX_STR_DIGITS: usize = 4300;
/// More significant bits than this always give more than `MAX_STR_DIGITS` decimal digits.
const MAX_INT_BITS: usize = 14_300;

pub const MULTI_QUOTES: [&str; 2] = ["\"\"\"", "'''"];
pub const ALL_QUOTES: [&str; 4] = ["'", "\"", "\"\"\"", "'''"];

/// `c.encode("unicode_escape").decode("ascii")` of one character.
fn unicode_escape(c: char, out: &mut String) {
    let point = u32::from(c);
    match c {
        '\\' => out.push_str("\\\\"),
        '\t' => out.push_str("\\t"),
        '\n' => out.push_str("\\n"),
        '\r' => out.push_str("\\r"),
        _ if point < 0x20 || (0x7f..0x100).contains(&point) => {
            out.push_str(&format!("\\x{point:02x}"));
        }
        _ if point < 0x80 => out.push(c),
        _ if point < 0x1_0000 => out.push_str(&format!("\\u{point:04x}")),
        _ => out.push_str(&format!("\\U{point:08x}")),
    }
}

/// `repr()` of a `str` in the Python of `minor` (`unicode_repr`).
pub fn repr_str(text: &str, minor: PyMinor) -> String {
    let mut out = String::with_capacity(text.len() + 2);
    archkeel_facts::pyrepr::string_with(text, &mut out, minor);
    out
}

/// `repr()` of a `bytes` value.
pub fn repr_bytes(bytes: &[u8]) -> String {
    let quote = if bytes.contains(&b'\'') && !bytes.contains(&b'"') {
        b'"'
    } else {
        b'\''
    };
    let mut out = String::with_capacity(bytes.len() + 3);
    out.push('b');
    out.push(char::from(quote));
    for &byte in bytes {
        match byte {
            _ if byte == quote || byte == b'\\' => {
                out.push('\\');
                out.push(char::from(byte));
            }
            b'\t' => out.push_str("\\t"),
            b'\n' => out.push_str("\\n"),
            b'\r' => out.push_str("\\r"),
            0x20..=0x7e => out.push(char::from(byte)),
            _ => out.push_str(&format!("\\x{byte:02x}")),
        }
    }
    out.push(char::from(quote));
    out
}

/// `repr()` of an `int` literal: the decimal digits, or `None` (`ValueError`) over 4 300 digits.
pub fn repr_int(token: &str) -> Option<String> {
    let lower = token.to_ascii_lowercase();
    let (radix, digits) = match lower.get(..2) {
        Some("0x") => (16, &lower[2..]),
        Some("0o") => (8, &lower[2..]),
        Some("0b") => (2, &lower[2..]),
        _ => (10, lower.as_str()),
    };
    let digits: Vec<u32> = digits
        .chars()
        .filter(|c| *c != '_')
        .map(|c| c.to_digit(radix))
        .collect::<Option<_>>()?;
    let first = digits.iter().position(|digit| *digit != 0);
    let Some(first) = first else {
        return Some("0".to_owned());
    };
    let digits = &digits[first..];
    let bits_per_digit = match radix {
        16 => 4,
        8 => 3,
        2 => 1,
        _ => 0,
    };
    let too_many = if radix == 10 {
        digits.len() > MAX_STR_DIGITS
    } else {
        digits.len().saturating_mul(bits_per_digit) > MAX_INT_BITS + bits_per_digit
    };
    if too_many {
        return None;
    }
    let text = decimal(digits, radix);
    (text.len() <= MAX_STR_DIGITS).then_some(text)
}

/// The decimal text of digits in `radix`, with limbs of 10^9.
fn decimal(digits: &[u32], radix: u32) -> String {
    const BASE: u64 = 1_000_000_000;
    let mut limbs: Vec<u64> = vec![0];
    for &digit in digits {
        let mut carry = u64::from(digit);
        for limb in &mut limbs {
            let value = *limb * u64::from(radix) + carry;
            *limb = value % BASE;
            carry = value / BASE;
        }
        while carry > 0 {
            limbs.push(carry % BASE);
            carry /= BASE;
        }
    }
    let mut text = String::new();
    for (index, limb) in limbs.iter().rev().enumerate() {
        if index == 0 {
            text.push_str(&limb.to_string());
        } else {
            text.push_str(&format!("{limb:09}"));
        }
    }
    text
}

/// `repr()` of a finite or infinite `float`, then the `1e309` of `ast.unparse` for infinity.
pub fn repr_float(value: f64, add_dot_zero: bool) -> String {
    if value.is_infinite() {
        return "1e309".to_owned();
    }
    // `{:e}` gives the shortest digits that read back: `1.5e-5`, `1e16`.
    let shortest = format!("{:e}", value.abs());
    let precision = shortest
        .split('e')
        .next()
        .unwrap_or("")
        .bytes()
        .filter(u8::is_ascii_digit)
        .count()
        .saturating_sub(1);
    // Explicit precision rounds ties to even; shortest formatting can choose the odd neighbour.
    let scientific = format!("{:.*e}", precision, value.abs());
    let (mantissa, exponent) = scientific.split_once('e').unwrap_or((&scientific, "0"));
    let exponent: i32 = exponent.parse().unwrap_or(0);
    let digits: String = mantissa.chars().filter(char::is_ascii_digit).collect();
    if digits.is_empty() {
        return "0.0".to_owned();
    }
    let sign = if value.is_sign_negative() { "-" } else { "" };
    let point = exponent + 1;
    let text = if (-3..=16).contains(&point) {
        fixed(&digits, point, add_dot_zero)
    } else {
        let (head, tail) = digits.split_at(digits.len().min(1));
        let fraction = if tail.is_empty() {
            String::new()
        } else {
            format!(".{tail}")
        };
        let sign = if exponent < 0 { '-' } else { '+' };
        format!("{head}{fraction}e{sign}{:02}", exponent.abs())
    };
    format!("{sign}{text}")
}

/// The digits with the decimal point after `point` digits (`point` from -3 to 16).
fn fixed(digits: &str, point: i32, add_dot_zero: bool) -> String {
    let count = i32::try_from(digits.len()).unwrap_or(i32::MAX);
    if point <= 0 {
        let zeros = "0".repeat(usize::try_from(-point).unwrap_or(0));
        return format!("0.{zeros}{digits}");
    }
    if point >= count {
        let zeros = "0".repeat(usize::try_from(point - count).unwrap_or(0));
        let tail = if add_dot_zero { ".0" } else { "" };
        return format!("{digits}{zeros}{tail}");
    }
    let (head, tail) = digits.split_at(usize::try_from(point).unwrap_or(0));
    format!("{head}.{tail}")
}

/// `repr()` of the `complex` value of an imaginary literal: its real part is 0.
pub fn repr_complex(imag: f64) -> String {
    format!("{}j", repr_float(imag, false))
}

/// `_str_literal_helper`: the escaped text and the quotes that can hold it, best first.
pub struct Quotes {
    pub text: String,
    pub quotes: Vec<&'static str>,
}

pub fn literal_helper(
    text: &str,
    quote_types: &[&'static str],
    escape_special_whitespace: bool,
    minor: PyMinor,
) -> Quotes {
    let mut escaped = String::with_capacity(text.len());
    for c in text.chars() {
        if !escape_special_whitespace && (c == '\n' || c == '\t') {
            escaped.push(c);
        } else if c == '\\' || !printable(c, minor) {
            unicode_escape(c, &mut escaped);
        } else {
            escaped.push(c);
        }
    }
    let mut possible: Vec<&'static str> = quote_types.to_vec();
    if escaped.contains('\n') {
        possible.retain(|quote| MULTI_QUOTES.contains(quote));
    }
    possible.retain(|quote| !escaped.contains(quote));
    if possible.is_empty() {
        let repr = repr_str(text, minor);
        let first = repr.chars().next().unwrap_or('\'');
        let quote = quote_types
            .iter()
            .copied()
            .find(|quote| quote.contains(first))
            .unwrap_or(if first == '"' { "\"" } else { "'" });
        let inner = repr
            .get(1..repr.len().saturating_sub(1))
            .unwrap_or_default();
        return Quotes {
            text: inner.to_owned(),
            quotes: vec![quote],
        };
    }
    if let Some(last) = escaped.chars().last() {
        // A stable sort: the quotes that do not start with the last character come first.
        possible.sort_by_key(|quote| quote.starts_with(last));
        if possible
            .first()
            .is_some_and(|quote| quote.starts_with(last))
        {
            escaped.pop();
            escaped.push('\\');
            escaped.push(last);
        }
    }
    Quotes {
        text: escaped,
        quotes: possible,
    }
}

/// `_write_str_avoiding_backslashes`.
pub fn avoiding_backslashes(text: &str, quote_types: &[&'static str], minor: PyMinor) -> String {
    let Quotes { text, quotes } = literal_helper(text, quote_types, false, minor);
    let quote = quotes.first().copied().unwrap_or("'");
    format!("{quote}{text}{quote}")
}

#[cfg(test)]
#[path = "literal_tests.rs"]
mod tests;
