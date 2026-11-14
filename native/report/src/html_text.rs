// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text and the glyphs of the report page (AD-496). One escape function protects each
//! dynamic text; the glyphs are fixed markup.

/// Escape a dynamic text for an HTML text or attribute position.
pub(super) fn escape(text: &str) -> String {
    let mut safe = String::new();
    for character in text.chars() {
        safe.push_str(match character {
            '&' => "&amp;",
            '<' => "&lt;",
            '>' => "&gt;",
            '"' => "&quot;",
            '\'' => "&#39;",
            _ => {
                safe.push(character);
                continue;
            }
        });
    }
    safe
}

/// The id of an HTML anchor from a component id: lower case, letters and digits only.
pub(super) fn anchor(prefix: &str, id: &str) -> String {
    let tail: String = id
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() {
                c.to_ascii_lowercase()
            } else {
                '-'
            }
        })
        .collect();
    format!("{prefix}{tail}")
}

/// The word `1 module` or `2 modules`.
pub(super) fn count(number: usize, singular: &str) -> String {
    let plural = match singular.strip_suffix('y') {
        Some(stem) => format!("{stem}ies"),
        None => format!("{singular}s"),
    };
    format!("{number} {}", if number == 1 { singular } else { &plural })
}

const ICON: &str = "<svg class=\"ak-icon\" viewBox=\"0 0 16 16\" aria-hidden=\"true\">";

/// A status glyph of the design system: the path of `PASS`, `FAIL` or `UNKNOWN`.
pub(super) fn status_icon(status: &str) -> String {
    let path = match status {
        "PASS" => "<path d=\"M3 8.5l3.2 3L13 4.5\"/>",
        "FAIL" => "<path d=\"M4 4l8 8M12 4l-8 8\"/>",
        _ => "<path d=\"M6 6.2a2.1 2.1 0 1 1 3 1.9c-.7.4-1 .8-1 1.6\"/><path d=\"M8 12.2v.01\"/>",
    };
    format!("{ICON}{path}</svg>")
}

/// The glyph of a level of the frame: `component`, `module` or `file`.
pub(super) fn level_icon(level: &str) -> String {
    let path = match level {
        "component" => "<rect x=\"3\" y=\"3\" width=\"10\" height=\"10\" rx=\"2.5\"/>",
        "module" => "<path d=\"M8 2l5.2 3v6L8 14l-5.2-3V5z\"/>",
        _ => "<path d=\"M4 2h5.5L12 4.5V14H4z\"/><path d=\"M9.5 2v2.5H12\"/>",
    };
    format!("{ICON}{path}</svg>")
}

const BASE64: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/// Standard base64 with padding, for the inline fonts.
pub(super) fn base64(bytes: &[u8]) -> String {
    let mut text = String::with_capacity(bytes.len().div_ceil(3) * 4);
    for chunk in bytes.chunks(3) {
        let [first, second, third] = [0, 1, 2].map(|i| chunk.get(i).copied());
        let group = (u32::from(first.unwrap_or(0)) << 16)
            | (u32::from(second.unwrap_or(0)) << 8)
            | u32::from(third.unwrap_or(0));
        let at = |shift: u32| char::from(BASE64[(group >> shift & 63) as usize]);
        text.push(at(18));
        text.push(at(12));
        text.push(if second.is_some() { at(6) } else { '=' });
        text.push(if third.is_some() { at(0) } else { '=' });
    }
    text
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_the_standard_form() {
        assert_eq!(base64(b""), "");
        assert_eq!(base64(b"f"), "Zg==");
        assert_eq!(base64(b"fo"), "Zm8=");
        assert_eq!(base64(b"foo"), "Zm9v");
        assert_eq!(base64(b"foobar"), "Zm9vYmFy");
    }

    #[test]
    fn a_count_has_its_plural() {
        assert_eq!(count(1, "module"), "1 module");
        assert_eq!(count(2, "dependency"), "2 dependencies");
    }
}
