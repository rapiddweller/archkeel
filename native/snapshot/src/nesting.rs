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
        if let Some(end) = raw_end(bytes, at) {
            at = end;
            continue;
        }
        match (byte, bytes.get(at + 1)) {
            (b'/', Some(b'/')) => {
                at += bytes[at..]
                    .iter()
                    .position(|b| *b == b'\n')
                    .unwrap_or(bytes.len() - at)
            }
            (b'/', Some(b'*')) => at = comment_end(bytes, at),
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
        match (bytes.get(at), bytes.get(at + 1)) {
            (Some(b'/'), Some(b'*')) => {
                depth += 1;
                at += 2;
            }
            (Some(b'*'), Some(b'/')) => {
                depth -= 1;
                at += 2;
            }
            _ => at += 1,
        }
    }
    at
}
