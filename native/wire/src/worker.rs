// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Private same-build worker protocol. Public wire replies carry no live authority.

use archkeel_facts::envelope::{ProfileLimits, Reply};
use archkeel_facts::ids::FactId;
use archkeel_facts::request::Request;
use archkeel_facts::{GapFact, Record, Section};
use flate2::read::ZlibDecoder;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::io::{self, BufRead, Read, Write};
use std::process::ExitCode;

use crate::protocol::{reply_version, Version};

/// Select the private worker entry point.
pub const RUST_WORKER_V1: &str = "--core-worker-v1";

/// Serve one request on the private channel, or let the binary use its public entry point.
pub fn serve_v1<Settings: Send + 'static, Limit: std::fmt::Display>(
    decode: impl FnOnce(&[u8]) -> Result<Request<Settings>, String>,
    test_features: &[&str],
    scan: impl FnOnce(&Request<Settings>, Version) -> Result<Result<Reply, String>, Limit>
        + Send
        + 'static,
) -> Option<ExitCode> {
    if std::env::args_os().nth(1).as_deref() != Some(std::ffi::OsStr::new(RUST_WORKER_V1)) {
        return None;
    }
    let mut payload = String::new();
    let answer = io::stdin()
        .lock()
        .take(1 << 20)
        .read_line(&mut payload)
        .map_err(|e| e.to_string())
        .and_then(|_| {
            if !payload.ends_with('\n') {
                return Err("incomplete worker request".into());
            }
            let request = decode(payload.as_bytes())?;
            if !test_features.is_empty() {
                return write_v1(io::stdout().lock(), Ok(Err("test-feature worker".into())));
            }
            // EOF means the parent has died or cancelled the scan.
            std::thread::spawn(|| {
                let mut byte = [0];
                let _ = io::stdin().read(&mut byte);
                std::process::exit(2);
            });
            let answer = std::thread::Builder::new()
                .stack_size(256 << 20)
                .spawn(move || {
                    scan(&request, reply_version(request.protocol_version))
                        .map_err(|limit| limit.to_string())
                })
                .map_err(|e| e.to_string())?
                .join()
                .map_err(|_| "worker panic")?;
            write_v1(io::stdout().lock(), answer)
        });
    Some(match answer {
        Ok(()) => ExitCode::SUCCESS,
        Err(why) => {
            let _ = write_v1(io::stdout().lock(), Ok(Err(why)));
            ExitCode::FAILURE
        }
    })
}
/// One worker response, before store validation.
#[derive(Serialize, Deserialize)]
enum Answer {
    /// The scan completed.
    Collected(Box<Packet>),
    /// The snapshot budget stopped the scan.
    ParseWork(String),
    /// The worker refused the scan.
    Refused(String),
}

/// A private transfer preserves facts that the public record encoding omits.
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Packet {
    reply: Reply,
    limits: ProfileLimits,
    premise: String,
    coverage_prefix: Option<usize>,
    unknown_dispatch: Vec<u32>,
    unknown_name_free: Vec<u32>,
    coverage_dispatch: Vec<u32>,
    coverage_name_free: Vec<u32>,
    inferred_receivers: BTreeSet<FactId>,
    excluded_sources: Vec<String>,
}

fn first_unknowns(sections: &[Section]) -> Option<&[Record<GapFact>]> {
    sections.iter().find_map(|section| match section {
        Section::Unknowns(gaps) => Some(gaps.as_slice()),
        _ => None,
    })
}

fn flag_slots<'a>(
    gaps: impl Iterator<Item = &'a Record<GapFact>>,
    pick: impl Fn(&Record<GapFact>) -> bool,
) -> Result<Vec<u32>, String> {
    let mut slots = Vec::new();
    for (index, gap) in gaps.enumerate() {
        if pick(gap) {
            let slot = u32::try_from(index).map_err(|_| "worker gap index exceeds u32")?;
            slots.push(slot);
        }
    }
    Ok(slots)
}

fn all_unknowns(sections: &[Section]) -> impl Iterator<Item = &Record<GapFact>> {
    sections
        .iter()
        .filter_map(|section| match section {
            Section::Unknowns(gaps) => Some(gaps.iter()),
            _ => None,
        })
        .flatten()
}

impl Packet {
    /// Take the assembled facts before applying the private producer statements.
    fn new(mut reply: Reply) -> Result<Self, String> {
        let gaps = &reply.facts.coverage.gaps;
        if gaps.iter().any(|g| g.data.data().code.is_some())
            || !reply.facts.owned_files.is_empty()
            || reply.facts.standard.is_some()
        {
            return Err("unsupported private worker fact".into());
        }
        let first = first_unknowns(&reply.facts.sections).unwrap_or(&[]);
        let coverage_prefix = (first.len() >= gaps.len()
            && first
                .get(..gaps.len())
                .is_some_and(|prefix| prefix == gaps.as_slice()))
        .then_some(gaps.len());
        let unknown_dispatch = flag_slots(all_unknowns(&reply.facts.sections), |g| {
            g.data.data().dispatch
        })?;
        let unknown_name_free = flag_slots(all_unknowns(&reply.facts.sections), |g| {
            g.data.data().no_name_route
        })?;
        let (coverage_dispatch, coverage_name_free) = if coverage_prefix.is_some() {
            reply.facts.coverage.gaps = Vec::new();
            (Vec::new(), Vec::new())
        } else {
            (
                flag_slots(gaps.iter(), |g| g.data.data().dispatch)?,
                flag_slots(gaps.iter(), |g| g.data.data().no_name_route)?,
            )
        };
        let inferred_receivers = reply
            .facts
            .sections
            .iter()
            .filter_map(|section| match section {
                Section::Imports(imports) => Some(imports),
                _ => None,
            })
            .flatten()
            .filter(|record| record.data.data().inferred_receiver)
            .map(|record| record.id.clone())
            .collect();
        let excluded_sources = std::mem::take(&mut reply.facts.excluded_sources);
        Ok(Self {
            limits: reply
                .facts
                .profile_limits
                .take()
                .ok_or("worker omitted profile limits")?,
            premise: reply
                .facts
                .scope_premise
                .take()
                .ok_or("worker omitted scope premise")?,
            reply,
            coverage_prefix,
            unknown_dispatch,
            unknown_name_free,
            coverage_dispatch,
            coverage_name_free,
            inferred_receivers,
            excluded_sources,
        })
    }

    /// Recover the two views of each gap and the original scope statements.
    fn finish(self) -> Result<Reply, String> {
        let Self {
            mut reply,
            limits,
            premise,
            coverage_prefix,
            unknown_dispatch,
            unknown_name_free,
            coverage_dispatch,
            coverage_name_free,
            mut inferred_receivers,
            excluded_sources,
        } = self;
        let mut unknowns: Vec<&mut Record<GapFact>> = Vec::new();
        for section in &mut reply.facts.sections {
            match section {
                Section::Unknowns(gaps) => unknowns.extend(gaps.iter_mut()),
                Section::Imports(imports) => imports
                    .iter_mut()
                    .filter(|record| inferred_receivers.remove(&record.id))
                    .for_each(|record| record.data.data_mut().inferred_receiver = true),
                _ => {}
            }
        }
        restore_dispatch_refs(&mut unknowns, &unknown_dispatch)?;
        restore_name_refs(&mut unknowns, &unknown_name_free)?;
        drop(unknowns);
        if let Some(count) = coverage_prefix {
            let first = first_unknowns(&reply.facts.sections)
                .and_then(|gaps| gaps.get(..count))
                .ok_or("unbound worker coverage prefix")?;
            reply.facts.coverage.gaps = first.to_vec();
        } else {
            let mut cov: Vec<&mut Record<GapFact>> = reply.facts.coverage.gaps.iter_mut().collect();
            restore_dispatch_refs(&mut cov, &coverage_dispatch)?;
            restore_name_refs(&mut cov, &coverage_name_free)?;
        }
        if !inferred_receivers.is_empty() {
            return Err("unbound worker receiver".into());
        }
        reply.facts.profile_limits = Some(limits);
        reply.facts.scope_premise = Some(premise);
        reply.facts.excluded_sources = excluded_sources;
        Ok(reply)
    }
}

fn restore_slots(
    gaps: &mut [&mut Record<GapFact>],
    slots: &[u32],
    missing: &str,
    apply: impl Fn(&mut Record<GapFact>) -> Result<(), String>,
) -> Result<(), String> {
    for &slot in slots {
        let gap = usize::try_from(slot)
            .ok()
            .and_then(|index| gaps.get_mut(index))
            .ok_or_else(|| missing.to_owned())?;
        apply(gap)?;
    }
    Ok(())
}

fn restore_name_refs(gaps: &mut [&mut Record<GapFact>], slots: &[u32]) -> Result<(), String> {
    restore_slots(gaps, slots, "unbound worker name-route proof", |gap| {
        let (GapFact::CollectionGap(data) | GapFact::SourceResolutionGap(data)) = &mut gap.data
        else {
            return Err("invalid name-route proof kind".into());
        };
        if data
            .source_module
            .as_ref()
            .zip(data.module.as_ref())
            .is_none_or(|(a, b)| a == b)
        {
            return Err("name-route proof needs a pair".into());
        }
        data.no_name_route = true;
        Ok(())
    })
}

fn restore_dispatch_refs(gaps: &mut [&mut Record<GapFact>], slots: &[u32]) -> Result<(), String> {
    restore_slots(gaps, slots, "unbound worker dispatch", |gap| {
        let GapFact::CollectionGap(data) = &mut gap.data else {
            return Err("invalid dispatch kind".into());
        };
        data.dispatch = true;
        Ok(())
    })
}

// A frame is 9 to 16 times the Rust source it covers (6.8 MB: 59 MiB; 5.8 MB of `std`: 86 MiB) and the
// scan budget is 64 MiB of source. A lower ceiling refuses projects that the linked collector scanned.
// Neither side reserves the length of a header: the buffers grow with the bytes that arrive.
const MAX_FRAME: usize = 1 << 30;
// Explicit ceiling on decompressed JSON bytes so a corrupt compressed frame cannot expand unboundedly.
const MAX_DECOMPRESSED_FRAME: u64 = 2 << 30;

struct BoundedReader<R> {
    inner: R,
    remaining: u64,
}

impl<R: Read> Read for BoundedReader<R> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        let count = self.inner.read(buf)?;
        let used = u64::try_from(count).unwrap_or(u64::MAX);
        if used > self.remaining {
            return Err(io::Error::other("worker frame exceeds decompressed limit"));
        }
        self.remaining -= used;
        Ok(count)
    }
}

fn decode_answer(payload: &[u8], max_decompressed: u64) -> Result<Answer, String> {
    let reader = BoundedReader {
        inner: ZlibDecoder::new(payload),
        remaining: max_decompressed,
    };
    serde_json::from_reader(reader).map_err(|e| e.to_string())
}

#[derive(Default)]
struct Frame(Vec<u8>);
impl Write for Frame {
    fn write(&mut self, part: &[u8]) -> io::Result<usize> {
        if part.len() > MAX_FRAME.saturating_sub(self.0.len()) {
            return Err(io::Error::other("worker frame exceeds 1 GiB"));
        }
        self.0.extend_from_slice(part);
        Ok(part.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

/// Write a version-one worker result. An outer error is a work limit; an inner error is a refusal.
fn write_v1(
    mut out: impl Write,
    result: Result<Result<Reply, String>, String>,
) -> Result<(), String> {
    let frame = {
        let answer = match result {
            Err(limit) => Answer::ParseWork(limit),
            Ok(Err(why)) => Answer::Refused(why),
            Ok(Ok(reply)) => Answer::Collected(Box::new(Packet::new(reply)?)),
        };
        let mut encoder = ZlibEncoder::new(Frame::default(), Compression::fast());
        serde_json::to_writer(&mut encoder, &answer).map_err(|e| e.to_string())?;
        encoder.finish().map_err(|e| e.to_string())?
    };
    let len = u32::try_from(frame.0.len()).map_err(|e| e.to_string())?;
    out.write_all(&len.to_be_bytes())
        .and_then(|()| out.write_all(&frame.0))
        .and_then(|()| out.flush())
        .map_err(|e| e.to_string())
}

/// Read exactly one bounded frame. Only the inner error denotes a parse-work refusal.
pub fn read_rust_v1(mut input: impl Read) -> Result<Result<Reply, String>, String> {
    let mut header = [0; 4];
    input
        .read_exact(&mut header)
        .map_err(|e| format!("the worker sent no frame: {e}"))?;
    let length = u32::from_be_bytes(header);
    if u64::from(length) > MAX_FRAME as u64 {
        return Err("worker frame exceeds 1 GiB".into());
    }
    let mut payload = Vec::new();
    input
        .by_ref()
        .take(u64::from(length))
        .read_to_end(&mut payload)
        .map_err(|e| e.to_string())?;
    if payload.len() as u64 != u64::from(length)
        || input.read(&mut [0]).map_err(|e| e.to_string())? != 0
    {
        return Err("wrong worker frame length".into());
    }
    let answer = decode_answer(&payload, MAX_DECOMPRESSED_FRAME)?;
    drop(payload);
    match answer {
        Answer::Collected(packet) => packet.finish().map(Ok),
        Answer::ParseWork(why) => Ok(Err(why)),
        Answer::Refused(why) => Err(why),
    }
}

#[cfg(test)]
#[path = "worker_tests.rs"]
mod tests;
