// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The 10.0.0 reply of the import survey: the reply that the Python collector writes in the phase
//! `imports` (`collect.collect`), with the typed records of `archkeel-facts` (AD-345).
//!
//! The survey is not the whole collection. The protocol says so with the capabilities of the
//! import survey (`PYTHON_IMPORT_SURVEY_SECTIONS`): the sections `imports` and `unknowns` only,
//! no resolution feature and no construct. The sections `symbols`, `calls`, `references`,
//! `bindings`, `typing_signals` and `constructs` are not declared, so they are not collected, and
//! the lists of the collection phase are empty. The host refuses a 10.0.0 reply, and the evaluation
//! refuses a Python reply with these capabilities (AD-334, AD-365).

use archkeel_facts::envelope::{Adapter, Coverage, Profile, Provenance, Runtime};
use archkeel_facts::request::PythonRequest;
use archkeel_facts::{GapFact, ImportFact};
use archkeel_snapshot::Snapshot;
use archkeel_wire::protocol::reply_version;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};

use crate::survey::Survey;
use crate::{inputs, requirement};

/// `PYTHON_IMPORT_SURVEY_SECTIONS`, in its order. No other section is collected.
pub const SURVEY_SECTIONS: [&str; 2] = ["imports", "unknowns"];

/// The version and the code digest of this binary (`archkeel-build-support`).
pub struct Build<'a> {
    pub version: &'a str,
    pub code_digest: &'a str,
}

/// The compressed 10.0.0 reply of one survey.
pub fn reply(
    request: &PythonRequest,
    survey: Survey,
    build: &Build<'_>,
) -> Result<Vec<u8>, String> {
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let selected = survey.coverage.selected_files.clone();
    let (inputs, source_digest) = inputs::inputs(&mut snapshot, &selected);
    let head = Head {
        provenance: provenance(request, &mut snapshot, build),
        git_head: request.snapshot.git_head.clone(),
        dirty: serde_json::to_value(&request.snapshot.dirty).map_err(|error| error.to_string())?,
        scope: request
            .scope
            .roots
            .iter()
            .map(|root| format!("{root}/**/*.py"))
            .collect(),
        sections: SURVEY_SECTIONS.to_vec(),
        features: Vec::new(),
        constructs: Vec::new(),
        inputs,
        source_digest: Some(source_digest),
        files: survey.files,
        imports: survey.targets,
    };
    let Survey {
        imports,
        unknowns,
        coverage,
        evidence,
        ..
    } = survey;
    same_coverage(&coverage, head.files.len())?;
    let mut bytes = Vec::new();
    encode_stream(
        reply_version(request.protocol_version),
        head,
        &mut bytes,
        |writer| {
            writer.write_typed_section::<ImportFact>(|emit| imports.iter().for_each(emit))?;
            writer.write_typed_section::<GapFact>(|emit| unknowns.iter().for_each(emit))?;
            Ok(Tail {
                selected_files: coverage.selected_files,
                files_read: usize::try_from(coverage.files_read).map_err(std::io::Error::other)?,
                gaps: coverage.gaps,
                evidence,
            })
        },
    )?;
    Ok(bytes)
}

/// The adapter of this binary, and the runtime that the Python collector claims: the version of
/// the interpreter block and the requirement of `pyproject.toml` (`runtime.collector_provenance`).
fn provenance(request: &PythonRequest, snapshot: &mut Snapshot, build: &Build<'_>) -> Provenance {
    let (required, requirement_state) = requirement::requirement(snapshot);
    Provenance {
        profile: Profile::Python,
        adapter: Adapter {
            code_digest: build.code_digest.to_owned(),
            name: Profile::Python.as_str().to_owned(),
            version: build.version.to_owned(),
        },
        runtime: Runtime {
            name: "python".to_owned(),
            required,
            requirement_state,
            version: request.resolver.interpreter.version.clone(),
        },
    }
}

/// The stream writes the coverage from its parts (`Coverage::of`). The reply must say what the
/// survey says, so a difference is an error and no reply.
fn same_coverage(coverage: &Coverage, files: usize) -> Result<(), String> {
    let files_read = usize::try_from(coverage.files_read).map_err(|error| error.to_string())?;
    let written = Coverage::of(
        (files_read, files),
        coverage.selected_files.clone(),
        coverage.gaps.clone(),
    );
    if written == *coverage {
        Ok(())
    } else {
        Err("the coverage of the reply differs from the coverage of the survey".to_owned())
    }
}

#[cfg(test)]
#[path = "reply_tests.rs"]
mod tests;
