// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Decode the protocol and the byte fields shared by core request kinds.

#[cfg(any(test, feature = "harness"))]
use crate::contract::InsideFile;
use serde::de::DeserializeOwned;
use serde::Deserialize;

/// The decompressed size limit of a reply in the dual run.
#[cfg(any(test, feature = "harness"))]
pub(crate) const INFLATE_LIMIT: u64 = 1 << 32;

/// One inside contract of a request: the reference of the mount, the repository-relative path
/// that the shell resolved it to, and the bytes in hex.
#[cfg(any(test, feature = "harness"))]
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct InsideJson {
    reference: String,
    identity: String,
    hex: String,
}

/// The protocol of a request, read before the fields that the protocol defines.
#[derive(Deserialize)]
struct Head {
    protocol: String,
}

#[cfg(any(test, feature = "harness"))]
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct ReplyBytes {
    pub(crate) hex: String,
}

/// A request of one protocol: the protocol is read before the fields that it defines. An error
/// is a request that the core cannot read.
pub(crate) fn decode<T: DeserializeOwned>(input: &[u8], protocol: &str) -> Result<T, String> {
    let head: Head =
        serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))?;
    if head.protocol != protocol {
        return Err(format!("unknown protocol {}", head.protocol));
    }
    serde_json::from_slice(input).map_err(|error| format!("invalid request: {error}"))
}

/// The inside contracts of the request, decoded. The whole request is already read, so the
/// bounds of the count and the size are checked in `contract::answer` and give a named refusal
/// (exit 3), not an unreadable request (AD-379).
#[cfg(any(test, feature = "harness"))]
pub(crate) fn insides(files: Vec<InsideJson>) -> Result<Vec<InsideFile>, String> {
    files
        .into_iter()
        .map(|file| {
            Ok(InsideFile {
                bytes: hex(&file.hex)?,
                reference: file.reference,
                identity: file.identity,
            })
        })
        .collect()
}

/// The bytes of a hex text.
#[cfg(any(test, feature = "harness"))]
pub(crate) fn hex(text: &str) -> Result<Vec<u8>, String> {
    let digits = text.as_bytes();
    if !digits.len().is_multiple_of(2) {
        return Err("the reply hex has an odd length".to_owned());
    }
    digits
        .chunks(2)
        .map(|pair| {
            let high = (pair[0] as char).to_digit(16);
            let low = (pair[1] as char).to_digit(16);
            match (high, low) {
                (Some(high), Some(low)) => u8::try_from(high * 16 + low)
                    .map_err(|_| "the reply hex is not a byte".to_owned()),
                _ => Err("the reply hex has a character that is not a hex digit".to_owned()),
            }
        })
        .collect()
}
