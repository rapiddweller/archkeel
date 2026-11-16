// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The 10.0.0 reply of the import survey: the reply that the Python collector writes in the phase
//! `imports` (`collect.collect`), with the typed records of `archkeel-facts` (AD-345).
//!
//! The survey is not the whole collection. The protocol says so with the capabilities of the
//! import survey and the written `assert` construct (AD-658). The linked path gives the same
//! survey as a typed reply (AD-450).

use archkeel_facts::envelope::{
    Adapter, Coverage, Evidence, Input, Profile, Provenance, Reply, Runtime, TargetSource,
};
use archkeel_facts::request::PythonRequest;
use archkeel_facts::{
    CallFact, ConstructFact, GapFact, ImportFact, Record, ReferenceFact, SymbolFact,
};
use archkeel_snapshot::Snapshot;
use archkeel_wire::protocol::reply_version;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};
use archkeel_wire::typed::assemble;

use crate::survey::{routes, Survey};
use crate::{inputs, requirement};

/// The sections of the survey, in their order. No other section is collected (AD-518 adds
/// `symbols`; the 4.0.1 survey has the first two).
pub(crate) const SURVEY_SECTIONS: [&str; 6] = [
    "imports",
    "unknowns",
    "symbols",
    "calls",
    "references",
    "constructs",
];

/// The version and the code digest of this binary (`archkeel-build-support`).
pub struct Build<'a> {
    /// The version of the binary.
    pub version: &'a str,
    /// The digest of the code of the binary.
    pub code_digest: &'a str,
}

/// The compressed 10.0.0 reply of one survey.
pub(crate) fn reply(
    request: &PythonRequest,
    survey: Survey,
    build: &Build<'_>,
    source: TargetSource,
) -> Result<Vec<u8>, String> {
    let (head, records) = parts(request, survey, build, source)?;
    let mut bytes = Vec::new();
    let version = reply_version(request.protocol_version);
    encode_stream(version, head, &mut bytes, |writer| records.produce(writer))?;
    Ok(bytes)
}

/// The same survey as the typed reply of the linked path: one head and one record producer.
pub(crate) fn typed(
    request: &PythonRequest,
    mut survey: Survey,
    build: &Build<'_>,
    source: TargetSource,
) -> Result<Reply, String> {
    // AD-504: the linked path also writes the publication routes that `interface_boundary` reads.
    // The subprocess reply stays the frozen survey of the phase `imports`.
    routes::resolve(
        &mut survey.imports,
        &survey.files,
        &survey.opaque_surface,
        &survey.sole_binders,
        &survey.ambiguous,
    );
    let (head, records) = parts(request, survey, build, source)?;
    assemble(reply_version(request.protocol_version), head, |writer| {
        records.produce(writer)
    })
}

/// The records of the sections and the tail of one survey.
struct Records {
    imports: Vec<Record<ImportFact>>,
    unknowns: Vec<Record<GapFact>>,
    symbols: Vec<Record<SymbolFact>>,
    calls: Vec<Record<CallFact>>,
    references: Vec<Record<ReferenceFact>>,
    constructs: Vec<Record<ConstructFact>>,
    coverage: Coverage,
    evidence: Vec<Evidence>,
}

impl Records {
    fn produce(self, writer: &mut impl SectionSink) -> std::io::Result<Tail> {
        writer.write_typed_section::<ImportFact>(|emit| self.imports.iter().for_each(emit))?;
        writer.write_typed_section::<GapFact>(|emit| self.unknowns.iter().for_each(emit))?;
        writer.write_typed_section::<SymbolFact>(|emit| self.symbols.iter().for_each(emit))?;
        writer.write_typed_section::<CallFact>(|emit| self.calls.iter().for_each(emit))?;
        writer
            .write_typed_section::<ReferenceFact>(|emit| self.references.iter().for_each(emit))?;
        writer
            .write_typed_section::<ConstructFact>(|emit| self.constructs.iter().for_each(emit))?;
        self.tail()
    }

    /// The tail of the stream: the coverage counts, the gaps and the evidence.
    fn tail(self) -> std::io::Result<Tail> {
        let files_read =
            usize::try_from(self.coverage.files_read).map_err(std::io::Error::other)?;
        Ok(Tail {
            measures: self.coverage.measures,
            selected_files: self.coverage.selected_files,
            files_read,
            gaps: self.coverage.gaps,
            evidence: self.evidence,
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
    source: TargetSource,
) -> Result<(Head, Records), String> {
    let mut snapshot = Snapshot::new(&request.snapshot.root);
    let selected = survey.coverage.selected_files.clone();
    let listings: Vec<(String, String)> = survey
        .listings
        .iter()
        .map(|listing| (listing.path.clone(), listing.text.clone()))
        .collect();
    let (inputs, source_digest) = inputs::with_listings(&mut snapshot, &selected, &listings);
    same_inputs(&inputs, &survey.parsed)?;
    let head = Head {
        provenance: provenance(request, &mut snapshot, build, source)?,
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
        constructs: vec![("assert", "supported")],
        inputs,
        source_digest: Some(source_digest),
        files: survey.files,
        imports: survey.targets,
    };
    same_coverage(&survey.coverage, head.files.len())?;
    let records = Records {
        imports: survey.imports,
        unknowns: survey.unknowns,
        symbols: survey.symbols,
        calls: survey.calls,
        references: survey.references,
        constructs: survey.constructs,
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
/// `Python 3.9 and 3.10 are` / `Python 3.10 is`: the versions of the range below 3.11.
fn unsupported_below(major: u32, minor: u32) -> String {
    let names: Vec<String> = (minor..=10).map(|each| format!("{major}.{each}")).collect();
    match names.as_slice() {
        [] => format!("Python {major}.{minor} is"),
        [one] => format!("Python {one} is"),
        [head @ .., last] => format!("Python {} and {last} are", head.join(", ")),
    }
}

fn provenance(
    request: &PythonRequest,
    snapshot: &mut Snapshot,
    build: &Build<'_>,
    source: TargetSource,
) -> Result<Provenance, String> {
    let (required, requirement_state) = requirement::requirement(snapshot);
    let interpreter = request
        .resolver
        .interpreter
        .as_ref()
        .ok_or("no Python target")?;
    let source_text = match source {
        TargetSource::Config => match &required {
            Some(text) => {
                format!("scan.python in archkeel.toml; requires-python {text:?} in pyproject.toml")
            }
            None => "scan.python in archkeel.toml".to_owned(),
        },
        TargetSource::Requirement => {
            let text = required
                .as_deref()
                .ok_or("the Python requirement changed")?;
            let mut said = format!("requires-python {text:?} in pyproject.toml");
            if let Some([major, minor, _]) = requirement::clamped_from(text) {
                said.push_str(&format!(
                    "; {} not supported, so the lowest supported version inside that range is used",
                    unsupported_below(major, minor)
                ));
            }
            said
        }
        TargetSource::Default => "the collector default".to_owned(),
        TargetSource::Legacy => String::new(),
    };
    let version = interpreter.version.as_str();
    let display_version = version.strip_suffix(".0").unwrap_or(version);
    let target_description = (source != TargetSource::Legacy).then(|| format!(
        "ArchKeel reads this project as Python {display_version} (from {source_text}); the collector supports Python 3.11–3.14"
    ));
    Ok(Provenance {
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
            version: version.to_owned(),
            target_source: (source != TargetSource::Legacy).then_some(source),
            target_description,
        },
    })
}

/// The stream writes the coverage from its parts (`Coverage::of`). The reply must say what the
/// survey says, so a difference is an error and no reply.
fn same_coverage(coverage: &Coverage, files: usize) -> Result<(), String> {
    let files_read = usize::try_from(coverage.files_read).map_err(|error| error.to_string())?;
    let mut written = Coverage::of(
        (files_read, files),
        coverage.selected_files.clone(),
        coverage.gaps.clone(),
    );
    written.measures.clone_from(&coverage.measures);
    if written == *coverage {
        Ok(())
    } else {
        Err("the coverage of the reply differs from the coverage of the survey".to_owned())
    }
}

#[cfg(test)]
#[path = "reply_tests.rs"]
mod tests;
