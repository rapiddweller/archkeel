// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The request and the typed reply of the survey (AD-454). The reply declares the sections
//! `imports` and `unknowns` only, as the import survey of the Python collector does.

use archkeel_facts::envelope::validation::{InterfaceNeed, Registered};
use archkeel_facts::envelope::{
    LimitSupport, OwnedFile, Profile, ProfileLimits, Provenance, Reply, SectionName, Validation,
};
use archkeel_facts::request::DartRequest;
use archkeel_facts::{GapFact, ImportFact};
use archkeel_wire::protocol::Version;
use archkeel_wire::stream::{Head, SectionSink, Tail};

use super::survey;

/// The sections of the survey reply, in their order. No other section is collected.
const SURVEY_SECTIONS: [&str; 2] = ["imports", "unknowns"];

/// The validation table of the survey (AD-688, AD-468): exactly the sections `imports` and
/// `unknowns`, no feature and no construct capability, and no interface statement. The standard
/// library is `dart`, and its owner also names the SDK libraries.
fn validation() -> Validation {
    Validation {
        registered: vec![Registered::of(
            &[SectionName::Imports, SectionName::Unknowns],
            &[],
        )],
        interface: InterfaceNeed::Unsupported,
        standard_library: Profile::Dart.as_str().to_owned(),
    }
}

/// Decode a Dart request with the shared wire, as the binary reads it on stdin.
pub fn decode(payload: &[u8]) -> Result<DartRequest, String> {
    archkeel_wire::request::decode_dart(payload)
}

/// The typed reply of one request: the survey with the sections `imports` and `unknowns`.
/// `provenance` names the build of the caller.
pub fn typed_reply(
    request: &DartRequest,
    provenance: Provenance,
    version: Version,
) -> Result<Reply, String> {
    let found = survey(request)?;
    let parts = found.parts;
    let parsed = found.coverage.files_parsed;
    let head = Head {
        provenance,
        git_head: request.snapshot.git_head.clone(),
        dirty: serde_json::to_value(&request.snapshot.dirty).map_err(|error| error.to_string())?,
        scope: found.scope,
        sections: SURVEY_SECTIONS.to_vec(),
        features: Vec::new(),
        constructs: Vec::new(),
        inputs: found.inputs,
        source_digest: None,
        files: found.files,
        imports: found.targets,
        validation: validation(),
    };
    let imports = found.imports;
    let tail = Tail {
        measures: None,
        selected_files: found.coverage.selected_files,
        files_read: usize::try_from(found.coverage.files_read).map_err(|e| e.to_string())?,
        gaps: found.unknowns,
        evidence: found.evidence,
    };
    let mut reply = archkeel_wire::typed::assemble(version, head, |writer| {
        writer.write_typed_section::<ImportFact>(|emit| imports.iter().for_each(emit))?;
        writer.write_typed_section::<GapFact>(|emit| tail.gaps.iter().for_each(emit))?;
        Ok(tail)
    })?;
    // AD-468: the survey reads no symbol and no interface, and each part names its owner.
    reply.facts.profile_limits = Some(ProfileLimits {
        dependency_symbols: LimitSupport::Unsupported,
        interface_boundary: LimitSupport::Unsupported,
    });
    // The wire counts a parsed file for each module; a part is a parsed file too (AD-468).
    reply.facts.coverage.files_parsed = parsed;
    reply.facts.owned_files = parts
        .into_iter()
        .map(|part| OwnedFile {
            rel_path: part.part,
            module: part.part_module,
            owner: part.module,
        })
        .collect();
    Ok(reply)
}
