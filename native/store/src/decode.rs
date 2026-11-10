// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The zlib frame of a protocol 8 or 9 reply, as `facts_codec.decode_response` reads it.

use std::io::{BufReader, Read};

use serde::Deserialize;

use archkeel_facts::envelope::Reply;
use flate2::bufread::ZlibDecoder;

/// The first byte of a zlib stream. Plain JSON never starts with it.
const ZLIB_CMF: u8 = 0x78;

/// The typed reply, read in one pass from the zlib stream: the JSON text is never held whole.
/// A stream that is longer than `limit`, truncated or followed by data fails.
pub(crate) fn reply(payload: &[u8], limit: u64) -> Result<Reply, String> {
    if payload.first() != Some(&ZLIB_CMF) {
        return Err(
            "the store reads only the compressed replies of protocols 8.0.0 and 9.0.0".to_owned(),
        );
    }
    let mut decoder = ZlibDecoder::new(payload);
    let decoded = {
        let reader = BufReader::new((&mut decoder).take(limit.saturating_add(1)));
        let mut json = serde_json::Deserializer::from_reader(reader);
        Reply::deserialize(&mut json).and_then(|reply| json.end().map(|()| reply))
    };
    if decoder.total_out() > limit {
        return Err(format!(
            "decompressed collection response exceeds its {limit} byte limit"
        ));
    }
    let reply = decoded.map_err(|error| match error.io_error_kind() {
        Some(_) => format!("invalid compressed collection response: {error}"),
        None => error.to_string(),
    })?;
    let mut rest = Vec::new();
    decoder
        .read_to_end(&mut rest)
        .map_err(|error| format!("invalid compressed collection response: {error}"))?;
    if !rest.is_empty() || !decoder.into_inner().is_empty() {
        return Err("compressed collection response is truncated or has trailing data".to_owned());
    }
    Ok(reply)
}
