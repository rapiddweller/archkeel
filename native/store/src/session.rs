// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The frames between the host and the store process (AD-346).
//!
//! The host starts one store process for one collection and writes frames to its stdin. A frame
//! is one tag byte, the payload length as 8 bytes big-endian, and the payload.
//!
//! 1. `R`: the collector reply. The answer is the read-set document.
//! 2. `B`: a binding request. The answer is the receipt digest.
//! 3. `D`: the parts of a member inventory binding. The answer is its digest.
//! 4. `W`: the parts of the observation. The answer is `architecture.json`.
//!
//! An answer has the tag `O` and its bytes, or `E` and a message. The end of stdin ends the
//! process. A frame that needs a reply before `R` is an error; the process keeps one reply.

use std::io::{self, Read, Write};

use crate::stored::Store;

/// The largest frame the host may send: the reply limit of the host times the inflate bound.
const FRAME_LIMIT: u64 = 1 << 40;

fn read_frame(input: &mut impl Read) -> io::Result<Option<(u8, Vec<u8>)>> {
    let mut tag = [0u8; 1];
    if input.read(&mut tag)? == 0 {
        return Ok(None);
    }
    let mut length = [0u8; 8];
    input.read_exact(&mut length)?;
    let length = u64::from_be_bytes(length);
    if length > FRAME_LIMIT {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "frame too long"));
    }
    let mut payload = Vec::new();
    input.take(length).read_to_end(&mut payload)?;
    if payload.len() as u64 != length {
        return Err(io::Error::new(
            io::ErrorKind::UnexpectedEof,
            "frame truncated",
        ));
    }
    Ok(Some((tag[0], payload)))
}

fn write_frame(output: &mut impl Write, answer: Result<Vec<u8>, String>) -> io::Result<()> {
    let (tag, bytes) = match answer {
        Ok(bytes) => (b'O', bytes),
        Err(message) => (b'E', message.into_bytes()),
    };
    output.write_all(&[tag])?;
    output.write_all(&(bytes.len() as u64).to_be_bytes())?;
    output.write_all(&bytes)?;
    output.flush()
}

/// Answer the frames of one collection until the end of `input`.
pub fn run(input: &mut impl Read, output: &mut impl Write, inflate_limit: u64) -> io::Result<()> {
    let mut store: Option<Store> = None;
    while let Some((tag, payload)) = read_frame(input)? {
        let answer = match (tag, &store) {
            (b'R', _) => match crate::ingest(&payload, inflate_limit) {
                Ok(kept) => {
                    drop(payload);
                    crate::seam::write_frame(kept.reply(), output).map_err(io::Error::other)?;
                    store = Some(kept);
                    continue;
                }
                Err(message) => Err(message),
            },
            (b'B', Some(kept)) => crate::bind(&payload, kept).map(String::into_bytes),
            (b'D', Some(kept)) => crate::digest(&payload, kept).map(String::into_bytes),
            (b'W', Some(kept)) => crate::write(payload, kept),
            (b'B' | b'D' | b'W', None) => Err("the store holds no reply".to_owned()),
            _ => Err(format!("unknown frame tag {tag}")),
        };
        write_frame(output, answer)?;
    }
    Ok(())
}

#[cfg(test)]
#[path = "session_tests.rs"]
mod tests;
