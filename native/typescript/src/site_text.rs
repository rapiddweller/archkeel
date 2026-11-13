// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Keep only bytes that the cross-file facts reference, not the whole parsed file (AD-420).

use crate::site_paths::Text;

pub(crate) fn compact(source: &[u8], texts: &mut [&mut Text]) -> Vec<u8> {
    for text in texts.iter_mut() {
        if source.get(text.start..text.end).is_none() {
            **text = Text::default();
        }
    }
    let mut ranges: Vec<Text> = texts
        .iter()
        .map(|text| **text)
        .filter(|text| !text.is_empty())
        .collect();
    ranges.sort_by_key(|text| (text.start, text.end));
    let mut merged: Vec<(Text, usize)> = Vec::new();
    for range in ranges {
        if let Some((last, _)) = merged
            .last_mut()
            .filter(|(last, _)| range.start <= last.end)
        {
            last.end = last.end.max(range.end);
        } else {
            merged.push((range, 0));
        }
    }
    let mut retained = Vec::new();
    for (range, offset) in &mut merged {
        *offset = retained.len();
        retained.extend_from_slice(source.get(range.start..range.end).unwrap_or(&[]));
    }
    for text in texts {
        if text.is_empty() {
            **text = Text::default();
            continue;
        }
        let index = merged
            .partition_point(|(range, _)| range.start <= text.start)
            .saturating_sub(1);
        if let Some((range, offset)) = merged.get(index) {
            let length = text.end - text.start;
            text.start = offset + text.start - range.start;
            text.end = text.start + length;
        }
    }
    retained
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overlapping_texts_keep_one_copy_and_their_exact_bytes() {
        let mut a = Text { start: 2, end: 7 };
        let mut b = Text { start: 4, end: 8 };
        let mut c = Text { start: 9, end: 10 };
        let source = b"//abcdef z";
        let retained = compact(source, &mut [&mut a, &mut b, &mut c]);
        assert_eq!(retained, b"abcdefz");
        assert_eq!(a.decode(&retained), "abcde");
        assert_eq!(b.decode(&retained), "cdef");
        assert_eq!(c.decode(&retained), "z");
    }
}
