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
//! the lists of the collection phase are empty (AD-334, AD-367). The linked path gives the same
//! survey as a typed reply (AD-450).

use archkeel_facts::envelope::{
    Adapter, Coverage, Evidence, Input, Profile, Provenance, Reply, Runtime,
};
use archkeel_facts::request::PythonRequest;
use archkeel_facts::{GapFact, ImportFact, Record};
use archkeel_snapshot::Snapshot;
use archkeel_wire::protocol::reply_version;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};
use archkeel_wire::typed::assemble;

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
    let (head, records) = parts(request, survey, build)?;
    let mut bytes = Vec::new();
    let version = reply_version(request.protocol_version);
    encode_stream(version, head, &mut bytes, |writer| records.produce(writer))?;
    Ok(bytes)
}

/// The same survey as the typed reply of the linked path: one head and one record producer.
pub fn typed(request: &PythonRequest, survey: Survey, build: &Build<'_>) -> Result<Reply, String> {
    let (head, records) = parts(request, survey, build)?;
    assemble(reply_version(request.protocol_version), head, |writer| {
        records.produce(writer)
    })
}

/// The records of the sections and the tail of one survey.
struct Records {
    imports: Vec<Record<ImportFact>>,
    unknowns: Vec<Record<GapFact>>,
    coverage: Coverage,
    evidence: Vec<Evidence>,
}

impl Records {
    fn produce(self, writer: &mut impl SectionSink) -> std::io::Result<Tail> {
        let Self {
            imports,
            unknowns,
            coverage,
            evidence,
        } = self;
        writer.write_typed_section::<ImportFact>(|emit| imports.iter().for_each(emit))?;
        writer.write_typed_section::<GapFact>(|emit| unknowns.iter().for_each(emit))?;
        Ok(Tail {
            selected_files: coverage.selected_files,
            files_read: usize::try_from(coverage.files_read).map_err(std::io::Error::other)?,
            gaps: coverage.gaps,
            evidence,
        })
    }
}

/// The head and the records of one survey. The inputs are read again here; each selected
/// input must have the digest of the bytes that the survey parsed, else the source changed
/// during the scan and there is no reply.
fn parts(
    request: &PythonRequest,
    survey: Survey,
    build: &Build<'_>,
) -> Result<(Head, Records), String> {
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let selected = survey.coverage.selected_files.clone();
    let (inputs, source_digest) = inputs::inputs(&mut snapshot, &selected);
    same_inputs(&inputs, &survey.parsed)?;
    let head = Head {
        provenance: provenance(request, &mut snapshot, build),
        git_head: request.snapshot.git_head.clone(),
        dirty: serde_json::to_value(&request.snapshot.dirty).map_err(|error| error.to_string())?,
        scope: request
            .scope
            .roots
            .iter()
            // The label of a scan root that the model binds to its settings (AD-450).
            .map(|root| format!("{root}/**"))
            .collect(),
        sections: SURVEY_SECTIONS.to_vec(),
        features: Vec::new(),
        constructs: Vec::new(),
        inputs,
        source_digest: Some(source_digest),
        files: survey.files,
        imports: survey.targets,
    };
    same_coverage(&survey.coverage, head.files.len())?;
    let records = Records {
        imports: survey.imports,
        unknowns: survey.unknowns,
        coverage: survey.coverage,
        evidence: survey.evidence,
    };
    Ok((head, records))
}

/// Each parsed file has an input with the digest of the parsed bytes.
fn same_inputs(inputs: &[Input], parsed: &[Input]) -> Result<(), String> {
    for file in parsed {
        if !inputs
            .iter()
            .any(|input| input.path == file.path && input.digest == file.digest)
        {
            return Err(format!("the source changed during the scan: {}", file.path));
        }
    }
    Ok(())
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
            version: request.resolver.interpreter.version.as_str().to_owned(),
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
