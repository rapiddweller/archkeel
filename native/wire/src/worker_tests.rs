// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use archkeel_facts::envelope::{
    validation::InterfaceNeed, LimitSupport, Profile, ProfileLimits, Provenance, Validation,
};
use archkeel_facts::ids::ModuleName;
use serde_json::Value;

use super::*;
use crate::protocol::Version;
use crate::stream::{Head, SectionSink, Tail};
use crate::typed::assemble;

fn pair_gap(id: &str, reason: &str, dispatch: bool, no_name_route: bool) -> Record<GapFact> {
    let mut gap = GapFact::collection(reason, "dst");
    if let GapFact::CollectionGap(data) = &mut gap {
        data.source_module = Some(ModuleName::new("src"));
        data.dispatch = dispatch;
        data.no_name_route = no_name_route;
    }
    Record::unknown(FactId::new(id), reason, None, "src", gap)
}

fn minimal_reply(first_gaps: Vec<Record<GapFact>>, extra_gaps: Vec<Record<GapFact>>) -> Reply {
    let head = Head {
        provenance: Provenance::native(
            Profile::Rust,
            ("0.0.0", &"d".repeat(64)),
            ("1.97.0", "1.97"),
        ),
        git_head: "a".repeat(40),
        dirty: Value::Bool(false),
        scope: vec!["src/**".to_owned()],
        sections: vec!["unknowns"],
        features: Vec::new(),
        constructs: Vec::new(),
        inputs: Vec::new(),
        source_digest: None,
        files: Vec::new(),
        imports: Vec::new(),
        validation: Validation {
            registered: Vec::new(),
            interface: InterfaceNeed::Nothing,
            standard_library: Profile::Rust.as_str().to_owned(),
        },
    };
    let coverage_gaps = first_gaps.clone();
    let mut reply = assemble(Version::V9, head, |writer| {
        writer.write_typed_section::<GapFact>(|emit| first_gaps.iter().for_each(emit))?;
        Ok(Tail {
            measures: None,
            selected_files: Vec::new(),
            files_read: 0,
            gaps: coverage_gaps,
            evidence: Vec::new(),
        })
    })
    .unwrap();
    if !extra_gaps.is_empty() {
        reply.facts.sections.push(Section::Unknowns(extra_gaps));
    }
    reply.facts.profile_limits = Some(ProfileLimits {
        dependency_symbols: LimitSupport::Supported,
        interface_boundary: LimitSupport::Supported,
        publication_surface: LimitSupport::Unsupported,
    });
    reply.facts.scope_premise = Some("premise".to_owned());
    reply
}

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

#[test]
fn round_trip_preserves_flags_across_multiple_unknowns_sections() {
    let gap_a = pair_gap("UNKNOWN-1", "first section gap", true, false);
    let gap_b = pair_gap("UNKNOWN-2", "second section gap", true, true);
    let reply = minimal_reply(vec![gap_a], vec![gap_b]);
    let mut frame = Vec::new();
    write_v1(&mut frame, Ok(Ok(reply))).unwrap();
    let restored = read_rust_v1(frame.as_slice()).unwrap().unwrap();
    assert_eq!(restored.facts.coverage.gaps.len(), 1);
    assert!(restored.facts.coverage.gaps[0].data.data().dispatch);
    assert!(!restored.facts.coverage.gaps[0].data.data().no_name_route);
    let sections: Vec<&[Record<GapFact>]> = restored
        .facts
        .sections
        .iter()
        .filter_map(|section| match section {
            Section::Unknowns(gaps) => Some(gaps.as_slice()),
            _ => None,
        })
        .collect();
    assert_eq!(sections.len(), 2);
    assert!(sections[0][0].data.data().dispatch);
    assert!(!sections[0][0].data.data().no_name_route);
    assert!(sections[1][0].data.data().dispatch);
    assert!(sections[1][0].data.data().no_name_route);
}

#[test]
fn decompressed_frame_limit_refuses_oversized_payloads() {
    let mut frame = Vec::new();
    write_v1(&mut frame, Ok(Err("x".repeat(4096)))).unwrap();
    let err = decode_answer(&frame[4..], 256).err().unwrap_or_default();
    assert!(err.contains("worker frame exceeds decompressed limit"));
}

#[test]
fn out_of_range_flag_slots_are_rejected() {
    let mut record = pair_gap("UNKNOWN-1", "pair gap", false, false);
    let mut refs = [&mut record];
    assert_eq!(
        restore_dispatch_refs(&mut refs, &[9]).unwrap_err(),
        "unbound worker dispatch"
    );
    assert_eq!(
        restore_name_refs(&mut refs, &[9]).unwrap_err(),
        "unbound worker name-route proof"
    );
}
