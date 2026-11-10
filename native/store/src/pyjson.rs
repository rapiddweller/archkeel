// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! JSON text equal to `json.dumps(value, sort_keys=True, ensure_ascii=False,
//! separators=(",", ":"))` of Python (`ir/codec_wire.write_json`).
//!
//! The keys of each object are sorted by code point; UTF-8 byte order is the same order. A text is
//! escaped as `json` escapes it with `ensure_ascii=False`: `serde_json` writes the same escapes.
//! A float is written as Python `repr` writes it.

use serde_json::Value;

/// `repr(value)` of a Python float. JSON holds no NaN and no infinity.
pub(crate) fn python_float(value: f64) -> Result<String, String> {
    if !value.is_finite() {
        return Err("a JSON number is not finite".to_owned());
    }
    // The shortest digits that read back as the same float, as `repr` chooses them.
    let scientific = format!("{:e}", value.abs());
    let (mantissa, exponent) = scientific
        .split_once('e')
        .ok_or("a float has no exponent")?;
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let exponent: i64 = exponent
        .parse()
        .map_err(|_| "a float exponent is invalid")?;
    // The position of the decimal point after the first digit, as in `format_float_short`.
    let point = exponent + 1;
    let sign = if value.is_sign_negative() { "-" } else { "" };
    let count = i64::try_from(digits.len()).map_err(|_| "a float has too many digits")?;
    let text = if !(-4 < point && point <= 16) {
        let (first, rest) = digits.split_at(1);
        let fraction = if rest.is_empty() {
            String::new()
        } else {
            format!(".{rest}")
        };
        let mark = if exponent < 0 { '-' } else { '+' };
        format!("{first}{fraction}e{mark}{:02}", exponent.abs())
    } else if point <= 0 {
        format!(
            "0.{}{digits}",
            "0".repeat(usize::try_from(-point).unwrap_or(0))
        )
    } else if point >= count {
        let zeros = "0".repeat(usize::try_from(point - count).unwrap_or(0));
        format!("{digits}{zeros}.0")
    } else {
        let (whole, fraction) = digits.split_at(usize::try_from(point).unwrap_or(0));
        format!("{whole}.{fraction}")
    };
    Ok(format!("{sign}{text}"))
}

/// A null, a Boolean or a number, with the spellings of JSON or of Python `repr` for the first
/// three. A number is written the same in both: an integer, or the `repr` of a float.
pub(crate) fn scalar(value: &Value, words: [&str; 3]) -> Result<String, String> {
    match value {
        Value::Null => Ok(words[0].to_owned()),
        Value::Bool(flag) => Ok(words[if *flag { 1 } else { 2 }].to_owned()),
        Value::Number(number) => number_text(number),
        _ => Err("a value is not a scalar".to_owned()),
    }
}

/// A JSON number as Python writes it: an integer, or the `repr` of a float.
pub(crate) fn number_text(number: &serde_json::Number) -> Result<String, String> {
    match (number.as_i64(), number.as_u64(), number.as_f64()) {
        (Some(int), _, _) => Ok(int.to_string()),
        (None, Some(int), _) => Ok(int.to_string()),
        (None, None, Some(float)) => python_float(float),
        (None, None, None) => Err("a number has no value".to_owned()),
    }
}

/// Write one JSON text with the escapes of Python `json` (`ensure_ascii=False`).
pub(crate) fn write_text(text: &str, out: &mut Vec<u8>) -> Result<(), String> {
    serde_json::to_writer(out, text).map_err(|error| error.to_string())
}

/// Writes the texts of a value. The canonical encoder replaces repeated texts by a reference.
pub(crate) trait Texts {
    fn write(&self, text: &str, out: &mut Vec<u8>) -> Result<(), String>;
}

/// Writes each text as it is.
pub(crate) struct Plain;

impl Texts for Plain {
    fn write(&self, text: &str, out: &mut Vec<u8>) -> Result<(), String> {
        write_text(text, out)
    }
}

/// Write `value` with sorted keys. `texts` writes each text value; a key is always plain.
pub(crate) fn write_value(
    value: &Value,
    texts: &dyn Texts,
    out: &mut Vec<u8>,
) -> Result<(), String> {
    match value {
        Value::String(text) => texts.write(text, out)?,
        Value::Array(items) => {
            out.push(b'[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push(b',');
                }
                write_value(item, texts, out)?;
            }
            out.push(b']');
        }
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort();
            out.push(b'{');
            for (index, key) in keys.into_iter().enumerate() {
                if index > 0 {
                    out.push(b',');
                }
                write_text(key, out)?;
                out.push(b':');
                write_value(&map[key.as_str()], texts, out)?;
            }
            out.push(b'}');
        }
        atom => out.extend_from_slice(scalar(atom, ["null", "true", "false"])?.as_bytes()),
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::python_float;

    #[test]
    fn a_float_is_written_as_python_repr_writes_it() -> Result<(), String> {
        let cases = [
            (0.0, "0.0"),
            (-0.0, "-0.0"),
            (1.0, "1.0"),
            (0.5, "0.5"),
            (100.0, "100.0"),
            (0.1, "0.1"),
            (1e-4, "0.0001"),
            (1e-5, "1e-05"),
            (1.5e-7, "1.5e-07"),
            (1e15, "1000000000000000.0"),
            (1e16, "1e+16"),
            (1.25e16, "1.25e+16"),
            (123456.789, "123456.789"),
            (1e300, "1e+300"),
            (-2.5, "-2.5"),
            (0.3333333333333333, "0.3333333333333333"),
        ];
        for (value, text) in cases {
            assert_eq!(python_float(value)?, text, "{value}");
        }
        Ok(())
    }
}
