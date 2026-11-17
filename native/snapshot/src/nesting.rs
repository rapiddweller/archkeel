// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A linear delimiter-depth check, separate from the linear input charge (AD-420).

pub(crate) fn over(bytes: &[u8], limit: usize) -> bool {
    let (mut at, mut depth, mut template) = (0, 0_usize, false);
    let mut expressions = Vec::new();
    while let Some(&byte) = bytes.get(at) {
        if template {
            match (byte, bytes.get(at + 1)) {
                (b'\\', _) => at += 2,
                (b'`', _) => {
                    template = false;
                    at += 1;
                }
                (b'$', Some(b'{')) => {
                    expressions.push(depth);
                    depth += 1;
                    template = false;
                    at += 2;
                }
                _ => at += 1,
            }
            if depth > limit {
                return true;
            }
            continue;
        }
        if let Some(end) = noncode_end(bytes, at) {
            at = end;
            continue;
        }
        match (byte, bytes.get(at + 1)) {
            (b'"' | b'\'', _) => at = quote_end(bytes, at, byte),
            (b'`', _) => {
                template = true;
                at += 1;
            }
            (b'(' | b'[' | b'{', _) => {
                depth += 1;
                at += 1;
            }
            (b')' | b']' | b'}', _) => {
                depth = depth.saturating_sub(1);
                if byte == b'}' && expressions.last() == Some(&depth) {
                    expressions.pop();
                    template = true;
                }
                at += 1;
            }
            _ => at += 1,
        }
        if depth > limit {
            return true;
        }
    }
    false
}

/// Maximum active operator work, including enclosing expressions but not sibling entries.
pub(crate) fn rust_operator_work(bytes: &[u8]) -> usize {
    let (mut at, mut active, mut peak) = (0, 0, 0);
    let mut groups = vec![0];
    while let Some(&byte) = bytes.get(at) {
        if let Some(end) = noncode_end(bytes, at) {
            at = end;
            continue;
        }
        match (byte, bytes.get(at + 1)) {
            (b'\'', _) if char_end(bytes, at).is_some() => {
                at = char_end(bytes, at).unwrap_or(at + 1);
            }
            (b'"', _) => at = rust_string_end(bytes, at),
            _ => {
                match byte {
                    b'(' | b'[' | b'{' => groups.push(0),
                    b')' | b']' | b'}' if groups.len() > 1 => {
                        active -= groups.pop().unwrap_or(0);
                    }
                    b',' | b';' => {
                        let last = groups.len() - 1;
                        active -= groups[last];
                        groups[last] = 0;
                    }
                    byte if b"+-*/%&|^=!<>?.".contains(&byte) || cast_operator(bytes, at) => {
                        active += 1;
                        let last = groups.len() - 1;
                        groups[last] += 1;
                        peak = peak.max(active);
                    }
                    _ => {}
                }
                at += 1;
            }
        }
    }
    peak
}

fn cast_operator(bytes: &[u8], at: usize) -> bool {
    fn word(byte: u8) -> bool {
        byte.is_ascii_alphanumeric() || byte == b'_' || !byte.is_ascii()
    }
    bytes.get(at..at + 2) == Some(b"as")
        && (at == 0 || !word(bytes[at - 1]))
        && bytes.get(at + 2).is_none_or(|byte| !word(*byte))
}

fn noncode_end(bytes: &[u8], at: usize) -> Option<usize> {
    if let Some(end) = raw_end(bytes, at) {
        return Some(end);
    }
    match bytes.get(at..at + 2) {
        Some(b"//") => Some(
            at + bytes[at..]
                .iter()
                .position(|byte| *byte == b'\n')
                .unwrap_or(bytes.len() - at),
        ),
        Some(b"/*") => Some(comment_end(bytes, at)),
        _ => None,
    }
}

fn rust_string_end(bytes: &[u8], from: usize) -> usize {
    let mut at = from + 1;
    while let Some(&byte) = bytes.get(at) {
        match byte {
            b'\\' => at += 2,
            b'"' => return at + 1,
            _ => at += 1,
        }
    }
    bytes.len()
}

fn char_end(bytes: &[u8], from: usize) -> Option<usize> {
    let rest = bytes.get(from + 1..)?;
    if rest.first() == Some(&b'\\') {
        let end = quote_end(bytes, from, b'\'');
        return (end > from + 2 && bytes.get(end - 1) == Some(&b'\'')).then_some(end);
    }
    let width = match *rest.first()? {
        0..=127 => 1,
        0xc2..=0xdf => 2,
        0xe0..=0xef => 3,
        0xf0..=0xf4 => 4,
        _ => return None,
    };
    std::str::from_utf8(rest.get(..width)?).ok()?;
    let end = from + 1 + width;
    (bytes.get(end) == Some(&b'\'')).then_some(end + 1)
}

fn quote_end(bytes: &[u8], from: usize, quote: u8) -> usize {
    let mut at = from + 1;
    while let Some(&byte) = bytes.get(at) {
        if byte == b'\\' {
            at += 2;
        } else if byte == quote {
            return at + 1;
        } else if byte == b'\n' {
            break;
        } else {
            at += 1;
        }
    }
    // An apostrophe without a closing quote can be a lifetime, not a string.
    if quote == b'\'' {
        from + 1
    } else {
        at.min(bytes.len())
    }
}

fn raw_end(bytes: &[u8], from: usize) -> Option<usize> {
    if bytes[from] != b'r' {
        return None;
    }
    let start = if from > 0 && b"bc".contains(&bytes[from - 1]) {
        from - 1
    } else {
        from
    };
    if start > 0 && (bytes[start - 1].is_ascii_alphanumeric() || bytes[start - 1] == b'_') {
        return None;
    }
    let hashes = bytes[from + 1..].iter().take_while(|b| **b == b'#').count();
    let quote = from + 1 + hashes;
    if bytes.get(quote) != Some(&b'"') {
        return None;
    }
    let mut at = quote + 1;
    while let Some(&byte) = bytes.get(at) {
        if byte == b'"'
            && bytes
                .get(at + 1..at + 1 + hashes)
                .is_some_and(|suffix| suffix.iter().all(|b| *b == b'#'))
        {
            return Some(at + 1 + hashes);
        }
        at += 1;
    }
    Some(bytes.len())
}

fn comment_end(bytes: &[u8], from: usize) -> usize {
    let (mut at, mut depth) = (from + 2, 1_usize);
    while at < bytes.len() && depth > 0 {
        match bytes.get(at..at + 2) {
            Some(b"/*") => depth += 1,
            Some(b"*/") => depth -= 1,
            _ => {
                at += 1;
                continue;
            }
        }
        at += 2;
    }
    at
}
