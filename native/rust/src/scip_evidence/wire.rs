// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Read bounded SCIP documents and their written occurrence ranges.

use std::io::{self, Read};

type Result<T> = std::result::Result<T, String>;

pub(super) fn varint(first: u8, input: &mut impl Read) -> Result<u64> {
    let mut result = u64::from(first & 127);
    let mut byte = first;
    for shift in (7..=63).step_by(7) {
        if byte & 128 == 0 {
            return Ok(result);
        }
        byte = read_byte(input)?.ok_or("truncated SCIP integer")?;
        if shift == 63 && byte > 1 {
            return Err("oversized SCIP integer".to_owned());
        }
        result |= u64::from(byte & 127) << shift;
    }
    Ok(result)
}

fn read_byte(input: &mut impl Read) -> Result<Option<u8>> {
    let mut byte = [0];
    match input.read(&mut byte) {
        Ok(0) => Ok(None),
        Ok(_) => Ok(Some(byte[0])),
        Err(error) => Err(format!("cannot read SCIP: {error}")),
    }
}

fn number(input: &mut impl Read) -> Result<u64> {
    varint(read_byte(input)?.ok_or("missing SCIP integer")?, input)
}

pub(super) fn documents(
    input: &mut impl Read,
    mut consume: impl FnMut(&[u8]) -> Result<()>,
) -> Result<()> {
    while let Some(first) = read_byte(input)? {
        let tag = varint(first, input)?;
        if tag & 7 != 2 || tag >> 3 == 0 {
            return Err("invalid SCIP index field".to_owned());
        }
        let length = number(input)?;
        if tag >> 3 == 2 {
            if length > 4 << 20 {
                return Err("SCIP document exceeds 4 MiB".to_owned());
            }
            let size = usize::try_from(length).map_err(|error| error.to_string())?;
            let mut document = vec![0; size];
            input
                .read_exact(&mut document)
                .map_err(|error| error.to_string())?;
            consume(&document)?;
        } else if io::copy(&mut input.take(length), &mut io::sink()).map_err(|e| e.to_string())?
            != length
        {
            return Err("truncated SCIP field".to_owned());
        }
    }
    Ok(())
}

pub(super) enum Field<'a> {
    Number(u64),
    Bytes(&'a [u8]),
    Other,
}

pub(super) fn field<'a>(input: &mut &'a [u8]) -> Result<(u64, Field<'a>)> {
    let tag = number(input)?;
    let value = match tag & 7 {
        0 => Field::Number(number(input)?),
        2 => {
            let size = usize::try_from(number(input)?).map_err(|error| error.to_string())?;
            let (value, rest) = input.split_at_checked(size).ok_or("truncated SCIP bytes")?;
            *input = rest;
            Field::Bytes(value)
        }
        kind @ (1 | 5) => {
            let size = if kind == 1 { 8 } else { 4 };
            let (_, rest) = input
                .split_at_checked(size)
                .ok_or("truncated SCIP fixed field")?;
            *input = rest;
            Field::Other
        }
        _ => return Err("invalid SCIP wire type".to_owned()),
    };
    if tag >> 3 == 0 {
        return Err("invalid SCIP field number".to_owned());
    }
    Ok((tag >> 3, value))
}

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub(super) struct Range(pub [u32; 4]);

pub(super) struct Occurrence<'a> {
    pub range: Option<Range>,
    pub symbol: &'a str,
    pub definition: bool,
    pub reference: bool,
}

pub(super) fn occurrence(mut bytes: &[u8]) -> Result<Occurrence<'_>> {
    let mut result = Occurrence {
        range: None,
        symbol: "",
        definition: false,
        reference: true,
    };
    let mut range = Vec::with_capacity(4);
    let mut typed = None;
    while !bytes.is_empty() {
        match field(&mut bytes)? {
            (1, Field::Bytes(mut values)) => {
                while !values.is_empty() {
                    push_offset(&mut range, number(&mut values)?)?;
                }
            }
            (1, Field::Number(value)) => push_offset(&mut range, value)?,
            (2, Field::Bytes(value)) if value.len() <= 1024 => {
                result.symbol = std::str::from_utf8(value).map_err(|error| error.to_string())?;
            }
            (2, Field::Bytes(_)) => return Err("SCIP symbol exceeds 1024 bytes".to_owned()),
            (3, Field::Number(roles)) => {
                result.definition = roles & 1 != 0 && roles & 0x50 == 0;
                result.reference = roles & 0x53 == 0;
            }
            (kind @ (8 | 9), Field::Bytes(fields)) if typed.is_none() => {
                typed = Some(typed_range(kind, fields)?);
            }
            (8 | 9, _) => return Err("duplicate or invalid SCIP typed range".to_owned()),
            _ => (),
        }
    }
    let legacy = match range.as_slice() {
        [line, start, end] => Some(Range([*line, *start, *line, *end])),
        &[a, b, c, d] => Some(Range([a, b, c, d])),
        [] => None,
        _ => return Err("invalid SCIP occurrence range".to_owned()),
    };
    if typed.zip(legacy).is_some_and(|(a, b)| a != b) {
        return Err("conflicting SCIP ranges".to_owned());
    }
    result.range = typed.or(legacy);
    if let Some(Range([sl, sc, el, ec])) = result.range {
        if (sl, sc) > (el, ec) {
            return Err("reversed SCIP occurrence range".to_owned());
        }
    }
    Ok(result)
}

fn typed_range(kind: u64, mut input: &[u8]) -> Result<Range> {
    let mut offsets = [0; 4];
    let mut seen = [false; 4];
    let fields = if kind == 8 { 3 } else { 4 };
    while !input.is_empty() {
        let (n, value) = field(&mut input)?;
        if n > fields {
            continue;
        }
        let i = usize::try_from(n - 1).map_err(|error| error.to_string())?;
        let Field::Number(value) = value else {
            return Err("SCIP typed position is not numeric".to_owned());
        };
        if std::mem::replace(&mut seen[i], true) {
            return Err("duplicate SCIP typed position".to_owned());
        }
        offsets[i] = offset(value)?;
    }
    if kind == 8 {
        offsets[3] = offsets[2];
        offsets[2] = offsets[0];
    }
    Ok(Range(offsets))
}

fn offset(value: u64) -> Result<u32> {
    let signed = i32::try_from(value).map_err(|error| error.to_string())?;
    u32::try_from(signed).map_err(|error| error.to_string())
}

fn push_offset(range: &mut Vec<u32>, value: u64) -> Result<()> {
    if range.len() >= 4 {
        return Err("invalid SCIP occurrence range length".to_owned());
    }
    range.push(offset(value)?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reads_legacy_ranges_and_withholds_invalid_ranges() {
        let raw = [10, 3, 1, 3, 9, 18, 1, b'f', 24, 1];
        let parsed = occurrence(&raw).expect("the occurrence has a valid legacy range");
        assert_eq!(parsed.range, Some(Range([1, 3, 1, 9])));
        assert_eq!(parsed.symbol, "f");
        assert!(parsed.definition);
        assert!(occurrence(&[10, 2, 1, 2]).is_err());
        assert!(occurrence(&[10, 5, 1, 2]).is_err());
        let typed = occurrence(&[66, 6, 8, 1, 16, 3, 24, 9]).expect("typed range");
        assert_eq!(typed.range, parsed.range);
        assert!(occurrence(&[10, 3, 1, 3, 9, 66, 0]).is_err());
        assert!(occurrence(&[10, 3, 1, 9, 3]).is_err());
    }

    #[test]
    fn streams_documents_and_refuses_truncated_fields() {
        let mut seen = Vec::new();
        documents(&mut &[10, 1, 0, 18, 1, 7, 18, 1, 9][..], |doc| {
            seen.extend_from_slice(doc);
            Ok(())
        })
        .expect("documents and metadata are complete");
        assert_eq!(seen, [7, 9]);
        assert!(documents(&mut &[18, 2, 7][..], |_| Ok(())).is_err());
        assert!(documents(&mut &[18, 128][..], |_| Ok(())).is_err());
    }
}
