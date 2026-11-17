// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The inline scripts of a page outside the scan roots that the repository guard reads (#1546).

/// The length of `<script`.
const SCRIPT_TAG: usize = 7;

/// The inline scripts of a page that run as JavaScript, each with a flag for `type="module"` and
/// with every byte outside the script blanked (a line end stays), so the lines stay the lines of
/// the page. A script with `src` holds no code of the page.
pub(crate) fn inline_scripts(data: &[u8]) -> Vec<(bool, Vec<u8>)> {
    let lower = data.to_ascii_lowercase();
    let mut found = Vec::new();
    let mut at = 0;
    while let Some(start) = find(&lower, b"<script", at) {
        let after = start + SCRIPT_TAG;
        let Some(close) = find(&lower, b">", after) else {
            break;
        };
        let attributes = String::from_utf8_lossy(&lower[after..close]).into_owned();
        let end = find(&lower, b"</script", close).unwrap_or(<[u8]>::len(data));
        at = end.max(close + 1);
        let tag = lower
            .get(after)
            .is_some_and(|b| b.is_ascii_whitespace() || *b == b'>');
        let kind = script_type(&attributes);
        if !tag || attributes.contains("src") || kind.is_none() {
            continue;
        }
        let mut program: Vec<u8> = data
            .iter()
            .map(|b| if *b == b'\n' { b'\n' } else { b' ' })
            .collect();
        if let (Some(slot), Some(code)) =
            (program.get_mut(close + 1..end), data.get(close + 1..end))
        {
            slot.copy_from_slice(code);
        }
        Vec::push(&mut found, (kind == Some(true), program));
    }
    found
}

/// The script type of an element: `Some(true)` for a module, `Some(false)` for a classic script,
/// `None` for data or a template.
fn script_type(attributes: &str) -> Option<bool> {
    let Some(at) = attributes.find("type") else {
        return Some(false);
    };
    let value: String = attributes[at + 4..]
        .trim_start()
        .trim_start_matches('=')
        .trim_start()
        .trim_start_matches(['"', '\''])
        .chars()
        .take_while(|c| !matches!(c, '"' | '\'' | ' ' | '>'))
        .collect();
    match String::as_str(&value) {
        "module" => Some(true),
        ""
        | "text/javascript"
        | "application/javascript"
        | "text/ecmascript"
        | "application/ecmascript"
        | "text/jsx"
        | "text/babel" => Some(false),
        _ => None,
    }
}

fn find(haystack: &[u8], needle: &[u8], from: usize) -> Option<usize> {
    haystack
        .get(from..)?
        .windows(<[u8]>::len(needle))
        .position(|window| window == needle)
        .map(|at| at + from)
}
