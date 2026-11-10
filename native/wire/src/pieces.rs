// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The pieces of a zlib stream that are compressed apart and joined (`stream.rs`).
//!
//! A piece is text that is compressed into raw deflate blocks of its own, with the Adler-32 sum and
//! the length of its text. Pieces that end with a sync flush end on a byte, so the blocks of
//! the next piece follow them; with one zlib header before the first and the sum of the whole text
//! after the last, a decoder reads the join as one stream.

use std::io::{self, Write};

use flate2::{Compress, Compression, FlushCompress, Status};

/// The size of the input that a piece compresses at one time.
const CHUNK: usize = 1 << 16;
/// The zlib header of the fastest level: deflate with a 32 KiB window, no dictionary.
pub(crate) const ZLIB_HEADER: [u8; 2] = [0x78, 0x01];

/// The checksum of zlib (Adler-32) of a piece of text, and how to join the checksums of pieces.
#[derive(Clone, Copy)]
pub(crate) struct Adler {
    low: u32,
    high: u32,
}

const ADLER_BASE: u32 = 65_521;
const ADLER_BASE_WIDE: u64 = 65_521;
/// The most bytes that the sums take before they must be reduced (`NMAX` of zlib).
const ADLER_STEP: usize = 5_552;

impl Adler {
    pub(crate) fn new() -> Self {
        Self { low: 1, high: 0 }
    }

    pub(crate) fn update(&mut self, data: &[u8]) {
        for step in data.chunks(ADLER_STEP) {
            for byte in step {
                self.low = self.low.wrapping_add(u32::from(*byte));
                self.high = self.high.wrapping_add(self.low);
            }
            self.low = self.low.wrapping_rem(ADLER_BASE);
            self.high = self.high.wrapping_rem(ADLER_BASE);
        }
    }

    pub(crate) fn value(self) -> u32 {
        self.high.wrapping_shl(16) | self.low
    }

    /// The checksum of the text `a` followed by a text `b` of `length` bytes (`adler32_combine`).
    pub(crate) fn join(first: u32, second: u32, length: u64) -> u32 {
        let base = ADLER_BASE_WIDE;
        let rest = length.wrapping_rem(ADLER_BASE_WIDE);
        let (first_low, first_high) =
            (u64::from(first & 0xffff), u64::from(first.wrapping_shr(16)));
        let (second_low, second_high) = (
            u64::from(second & 0xffff),
            u64::from(second.wrapping_shr(16)),
        );
        let low = first_low
            .wrapping_add(second_low)
            .wrapping_add(base)
            .wrapping_sub(1)
            .wrapping_rem(ADLER_BASE_WIDE);
        let high = rest
            .wrapping_mul(first_low)
            .wrapping_add(first_high)
            .wrapping_add(second_high)
            .wrapping_add(base.wrapping_sub(rest))
            .wrapping_rem(ADLER_BASE_WIDE);
        let joined = low | high.wrapping_shl(16);
        u32::try_from(joined).unwrap_or(0)
    }
}

/// A piece of the reply: text that is compressed into raw deflate blocks of its own.
pub(crate) struct Piece {
    engine: Compress,
    input: Vec<u8>,
    packed: Vec<u8>,
    adler: Adler,
    length: u64,
}

/// A closed piece: its deflate blocks, the checksum of its text and the length of its text.
pub(crate) struct Packed {
    pub(crate) bytes: Vec<u8>,
    pub(crate) adler: u32,
    pub(crate) length: u64,
}

impl Piece {
    pub(crate) fn new() -> Self {
        Self {
            engine: Compress::new(Compression::new(1), false),
            input: Vec::with_capacity(CHUNK),
            packed: Vec::new(),
            adler: Adler::new(),
            length: 0,
        }
    }

    /// Compress the input that waits, with `flush`; a piece that ends here uses `Sync` (the blocks
    /// end on a byte) or `Finish` (the last block).
    fn pack(&mut self, flush: FlushCompress) -> io::Result<()> {
        let input = std::mem::take(&mut self.input);
        let mut done = 0;
        let mut idle = 0_u32;
        loop {
            self.packed.reserve(CHUNK);
            let (before_in, before_out) = (self.engine.total_in(), self.engine.total_out());
            let status = self
                .engine
                .compress_vec(input.get(done..).unwrap_or(&[]), &mut self.packed, flush)
                .map_err(io::Error::other)?;
            done = done.wrapping_add(
                usize::try_from(self.engine.total_in().wrapping_sub(before_in)).unwrap_or(0),
            );
            let produced = self.engine.total_out().wrapping_sub(before_out);
            let finished = match flush {
                FlushCompress::Finish => status == Status::StreamEnd,
                // The output of a flush is complete when the call left room in the buffer.
                _ => done == input.len() && self.packed.len() < self.packed.capacity(),
            };
            if finished || (done == input.len() && produced == 0 && flush == FlushCompress::None) {
                break;
            }
            idle = if produced == 0 && done == input.len() {
                idle.saturating_add(1)
            } else {
                0
            };
            if idle > 8 {
                return Err(io::Error::other("the compressor made no progress"));
            }
        }
        let mut input = input;
        input.clear();
        self.input = input;
        Ok(())
    }

    pub(crate) fn close(mut self, last: bool) -> io::Result<Packed> {
        self.pack(if last {
            FlushCompress::Finish
        } else {
            FlushCompress::Sync
        })?;
        Ok(Packed {
            bytes: self.packed,
            adler: self.adler.value(),
            length: self.length,
        })
    }
}

impl Write for Piece {
    fn write(&mut self, data: &[u8]) -> io::Result<usize> {
        self.adler.update(data);
        self.length = self
            .length
            .wrapping_add(u64::try_from(data.len()).unwrap_or(u64::MAX));
        self.input.extend_from_slice(data);
        if self.input.len() >= CHUNK {
            self.pack(FlushCompress::None)?;
        }
        Ok(data.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::io::Read;

    use flate2::read::ZlibDecoder;

    use super::*;

    fn sum(text: &[u8]) -> (u32, u64) {
        let mut adler = Adler::new();
        adler.update(text);
        (adler.value(), text.len() as u64)
    }

    #[test]
    fn the_sum_of_a_join_is_the_sum_of_the_whole_text() {
        // Texts that are shorter than, equal to and longer than the step of the sum.
        for (first, second) in [(0, 0), (1, 0), (0, 7), (100, 5_552), (6_000, 70_000)] {
            let a: Vec<u8> = (0..first).map(|n| (n * 7 % 251) as u8).collect();
            let b: Vec<u8> = (0..second).map(|n| (n * 13 % 253) as u8).collect();
            let whole = [a.clone(), b.clone()].concat();
            let (left, right) = (sum(&a).0, sum(&b));
            assert_eq!(Adler::join(left, right.0, right.1), sum(&whole).0);
        }
    }

    #[test]
    fn pieces_that_are_joined_are_one_zlib_stream() {
        let texts: [&[u8]; 3] = [b"{\"a\":[", &[b'x'; 200_000], b"]}"];
        let mut packed = Vec::new();
        for (index, text) in texts.into_iter().enumerate() {
            let mut piece = Piece::new();
            piece.write_all(text).unwrap();
            packed.push(piece.close(index == 2).unwrap());
        }
        let inner = Adler::join(packed[0].adler, packed[1].adler, packed[1].length);
        let whole = Adler::join(inner, packed[2].adler, packed[2].length);
        let mut stream = ZLIB_HEADER.to_vec();
        for part in &packed {
            stream.extend_from_slice(&part.bytes);
        }
        stream.extend_from_slice(&whole.to_be_bytes());
        let mut text = Vec::new();
        ZlibDecoder::new(stream.as_slice())
            .read_to_end(&mut text)
            .unwrap();
        assert_eq!(text, texts.concat());
    }
}
