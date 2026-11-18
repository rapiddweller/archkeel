// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Private same-build worker protocol. Public wire replies carry no live authority.

use archkeel_facts::envelope::{ProfileLimits, Reply};
use archkeel_facts::ids::FactId;
use archkeel_facts::request::Request;
use archkeel_facts::{GapFact, Record, Section};
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
    dispatch: BTreeSet<FactId>,
    inferred_receivers: BTreeSet<FactId>,
    name_free_gaps: BTreeSet<FactId>,
}
impl Packet {
    /// Take the assembled facts before applying the private producer statements.
    fn new(mut reply: Reply) -> Result<Self, String> {
        let gaps = &reply.facts.coverage.gaps;
        if gaps.iter().any(|g| g.data.data().code.is_some())
            || !reply.facts.excluded_sources.is_empty()
            || !reply.facts.owned_files.is_empty()
            || reply.facts.standard.is_some()
        {
            return Err("unsupported private worker fact".into());
        }
        let dispatch = gaps
            .iter()
            .filter(|g| g.data.data().dispatch)
            .map(|g| g.id.clone())
            .collect();
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
        let name_free_gaps = reply
            .facts
            .sections
            .iter()
            .filter_map(|section| {
                if let Section::Unknowns(gaps) = section {
                    Some(gaps)
                } else {
                    None
                }
            })
            .flatten()
            .filter(|gap| gap.data.data().no_name_route)
            .map(|gap| gap.id.clone())
            .collect();
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
            dispatch,
            inferred_receivers,
            name_free_gaps,
        })
    }
    /// Recover the two views of each gap and the original scope statements.
    fn finish(self) -> Result<Reply, String> {
        let Self {
            mut reply,
            limits,
            premise,
            dispatch,
            mut inferred_receivers,
            name_free_gaps,
        } = self;
        restore(&mut reply.facts.coverage.gaps, &dispatch)?;
        restore_names(&mut reply.facts.coverage.gaps, &name_free_gaps)?;
        let mut named = 0;
        for s in &mut reply.facts.sections {
            match s {
                Section::Unknowns(gaps) => {
                    restore(gaps, &dispatch)?;
                    named += restore_names(gaps, &name_free_gaps)?;
                }
                Section::Imports(imports) => imports
                    .iter_mut()
                    .filter(|record| inferred_receivers.remove(&record.id))
                    .for_each(|record| record.data.data_mut().inferred_receiver = true),
                _ => {}
            }
        }
        if !inferred_receivers.is_empty() {
            return Err("unbound worker receiver".into());
        }
        if named != name_free_gaps.len() {
            return Err("unbound worker name-route proof".into());
        }
        reply.facts.profile_limits = Some(limits);
        reply.facts.scope_premise = Some(premise);
        Ok(reply)
    }
}

fn restore_names(
    gaps: &mut [Record<GapFact>],
    name_free: &BTreeSet<FactId>,
) -> Result<usize, String> {
    let mut seen = 0;
    for gap in gaps.iter_mut().filter(|gap| name_free.contains(&gap.id)) {
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
        seen += 1;
    }
    Ok(seen)
}

fn restore(gaps: &mut [Record<GapFact>], dispatch: &BTreeSet<FactId>) -> Result<(), String> {
    let mut seen = 0;
    for g in gaps.iter_mut().filter(|g| dispatch.contains(&g.id)) {
        let GapFact::CollectionGap(d) = &mut g.data else {
            return Err("invalid dispatch kind".into());
        };
        d.dispatch = true;
        seen += 1;
    }
    if seen != dispatch.len() {
        return Err("unbound worker dispatch".into());
    }
    Ok(())
}

// A frame is 9 to 16 times the Rust source it covers (6.8 MB: 59 MiB; 5.8 MB of `std`: 86 MiB) and the
// scan budget is 64 MiB of source. A lower ceiling refuses projects that the linked collector scanned.
// Neither side reserves the length of a header: the buffers grow with the bytes that arrive.
const MAX_FRAME: usize = 1 << 30;

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
    let answer = match result {
        Err(limit) => Answer::ParseWork(limit),
        Ok(Err(why)) => Answer::Refused(why),
        Ok(Ok(reply)) => Answer::Collected(Box::new(Packet::new(reply)?)),
    };
    let mut frame = Frame::default();
    serde_json::to_writer(&mut frame, &answer).map_err(|e| e.to_string())?;
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
    match serde_json::from_slice(&payload).map_err(|e| e.to_string())? {
        Answer::Collected(packet) => packet.finish().map(Ok),
        Answer::ParseWork(why) => Ok(Err(why)),
        Answer::Refused(why) => Err(why),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn the_frame_refuses_overflow_before_reading_the_body() {
        let header = u32::MAX.to_be_bytes();
        assert_eq!(
            read_rust_v1(header.as_slice()).unwrap_err(),
            "worker frame exceeds 1 GiB"
        );
    }
    #[test]
    fn a_refusal_frame_gives_its_reason_and_an_empty_stream_gives_no_frame() {
        let mut frame = Vec::new();
        write_v1(&mut frame, Ok(Err("the reason".into()))).unwrap();
        assert_eq!(read_rust_v1(frame.as_slice()).unwrap_err(), "the reason");
        assert!(read_rust_v1(&[][..])
            .unwrap_err()
            .starts_with("the worker sent no frame"));
    }
    #[test]
    fn only_a_complete_single_frame_can_return_a_work_refusal() {
        let mut frame = Vec::new();
        write_v1(&mut frame, Err("work limit".into())).unwrap();
        assert_eq!(
            read_rust_v1(frame.as_slice()).unwrap().unwrap_err(),
            "work limit"
        );
        for end in 0..frame.len() {
            assert!(read_rust_v1(&frame[..end]).is_err());
        }
        frame.push(0);
        assert!(read_rust_v1(frame.as_slice()).is_err());
    }
}
