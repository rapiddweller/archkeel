// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of PR 4.3a-3a: the imports expanded to one record for each bound name
//! (`_named_imports`, `_export_binding`) and the string comparisons (`_constructs`).
//!
//! The reply carries them under the capability `inner-uml-v1` (AD-340). The `dump` feature prints them, and
//! `tests/test_collector_native_records.py` compares them with the unmodified Python collector.
//! The evidence that the new records cite is kept apart, so the evidence of the reply is unchanged.

use std::io::{self, Write};

use archkeel_facts::envelope::validation::{InterfaceNeed, Registered};
use archkeel_facts::envelope::{ConstructSupport, Profile, SectionName, Validation};
use archkeel_facts::{
    BindingFact, CallFact, ConstructFact, ImportFact, IntoSection, Record, ReferenceFact,
    SymbolFact,
};
use archkeel_wire::protocol::Version;
use archkeel_wire::stream::{encode_stream, Head, SectionSink, Tail};

use crate::bound_names::expand;
use crate::cited::Cited;
use crate::collected::{Facts, Records};
use crate::construct_records::{constructs, STRING_LITERAL_COMPARE};
use crate::kept::Pending;
use crate::resolution::{local_imports, Imports};
use crate::script_effects::effect_record;
use crate::site_records::{self, Pass};
use crate::symbol_table::SymbolTable;
use crate::symbols;

/// The assumption that the proofs of a script global rest on (AD-540, amended by #1546). The report
/// states it with the verdict. The collector cannot see code outside the repository; a file of the
/// repository outside the scan roots that replaces a global is read (`script_outside.rs`).
const SCRIPT_PREMISE: &str =
    "code outside the scan roots hands in no global or platform object and replaces no global";

/// The premise of a run whose repository guard applied a stated generated copy (AD-788).
const SCRIPT_PREMISE_GENERATED: &str = "code outside the scan roots hands in no global or \
     platform object and replaces no global, and a stated generated copy is the code of its sources";

/// The import features that each registered set of the collector states (`native` set).
const NATIVE_IMPORTS: [&str; 4] = [
    "literal-imports",
    "relative-specifiers",
    "node-builtins",
    "local-runtime-closure",
];

/// The validation table of the collector (AD-688; the registered sets of AD-378, lead decision
/// L-35a, `check/evaluation/evaluate.py:1031-1054`): the four native import features with the
/// sections `imports` and `unknowns`; or the inner UML set (those features and `inner-uml-v1`,
/// optionally `script-globals-v1`) with the six inner UML sections and no construct capability,
/// or with the `constructs` section and exactly `string_literal_compare` `partial`. Each set may
/// state `bundler-mode-v1`. An interface statement needs no feature; the standard library is
/// empty.
pub(crate) fn validation() -> Validation {
    use SectionName::{Bindings, Calls, Constructs, Imports, References, Symbols, Unknowns};
    let bundler = ["bundler-mode-v1"];
    let inner_features: Vec<&str> = NATIVE_IMPORTS.into_iter().chain(["inner-uml-v1"]).collect();
    let inner_optional = ["bundler-mode-v1", "script-globals-v1"];
    let inner = [Imports, Unknowns, Symbols, Calls, References, Bindings];
    let with_constructs = [
        Imports, Unknowns, Symbols, Calls, References, Bindings, Constructs,
    ];
    Validation {
        registered: vec![
            Registered::of(&[Imports, Unknowns], &NATIVE_IMPORTS).with_optional_features(&bundler),
            Registered::of(&inner, &inner_features).with_optional_features(&inner_optional),
            Registered::of(&with_constructs, &inner_features)
                .with_optional_features(&inner_optional)
                .with_construct(STRING_LITERAL_COMPARE, &[ConstructSupport::Partial]),
        ],
        interface: InterfaceNeed::Nothing,
        standard_library: Profile::TypeScript.as_str().to_owned(),
    }
}

/// What the producer holds before the first record is written: the targets of the imports, the
/// table of symbols and the evidence, which the records cite while they are written.
pub(crate) struct Plan<'p> {
    pending: &'p Pending,
    table: SymbolTable<'p>,
    imports: Imports,
    expanded: Records,
    cited: Cited,
    gaps: Vec<Record<archkeel_facts::GapFact>>,
    selected_files: Vec<String>,
    files_read: usize,
}

/// The one producer of the reply (AD-340, PR 4.3a-3d): the head, and the plan whose `write` gives
/// each section to a sink. The stream of the reply and the lists of the tests and the dump both run
/// this code, so a record that it drops or changes is dropped or changed in both. `track` keeps the
/// ids of the cited evidence, which only the dump needs.
pub(crate) fn plan(mut facts: Facts, pending: &Pending, track: bool) -> (Head, Plan<'_>) {
    let mut cited = Cited::owning(std::mem::take(&mut facts.evidence), track);
    let mut expanded = Records::default();
    expand(&facts, pending, &mut cited, &mut expanded);
    // The script analysis comes after the named imports and before the symbols, as in Python.
    for (rel, span) in &pending.script.cites {
        cited.cite(rel, span);
    }
    if !expanded.witnesses.is_empty() || pending.dependency_scope {
        let at = facts
            .features
            .iter()
            .position(|name| *name == "inner-uml-v1");
        facts.features.insert(
            at.map_or(facts.features.len(), |at| at.saturating_add(1)),
            "script-globals-v1",
        );
    }
    expanded
        .imports
        .sort_by(|left, right| left.id.cmp(&right.id));
    let imports = local_imports(pending, &facts);
    let head = Head {
        provenance: facts.provenance.clone(),
        git_head: facts.git_head.clone(),
        dirty: facts.dirty.clone(),
        scope: std::mem::take(&mut facts.scope),
        sections: sections(),
        features: std::mem::take(&mut facts.features),
        constructs: vec![(STRING_LITERAL_COMPARE, "partial")],
        inputs: std::mem::take(&mut facts.inputs),
        source_digest: None,
        files: std::mem::take(&mut facts.files),
        imports: std::mem::take(&mut expanded.targets),
        validation: validation(),
    };
    let plan = Plan {
        pending,
        table: SymbolTable::build(pending),
        imports,
        expanded,
        cited,
        gaps: std::mem::take(&mut facts.gaps),
        selected_files: std::mem::take(&mut facts.selected_files),
        files_read: facts.files_read,
    };
    (head, plan)
}

impl Plan<'_> {
    /// Write the sections in the order of the capability. The records of the symbols, the calls and
    /// the references are made and given one at a time, so the records of a project are never alive
    /// together. The evidence is cited in the order of Python: imports, symbols, calls, references,
    /// constructs. The tail has the evidence; the second value has the ids that the records cited.
    pub(crate) fn write(mut self, sink: &mut impl SectionSink) -> io::Result<(Tail, Vec<String>)> {
        let Self {
            pending,
            table,
            imports,
            expanded,
            cited,
            gaps,
            ..
        } = &mut self;
        sink.write_typed_section::<ImportFact>(|emit| expanded.imports.iter().for_each(emit))?;
        sink.write_typed_section::<archkeel_facts::GapFact>(|emit| gaps.iter().for_each(emit))?;
        sink.write_typed_section::<SymbolFact>(|emit| {
            symbols::each(table, cited, &mut |record| emit(&record));
        })?;
        let mut head = pending.script.publications.clone();
        head.extend(std::mem::take(&mut expanded.witnesses));
        let mut placed = Vec::new();
        sink.write_typed_section::<CallFact>(|emit| {
            placed.extend(site_records::pass(
                table,
                pending,
                imports,
                cited,
                Pass::Calls(emit),
            ));
        })?;
        sink.write_typed_section::<ReferenceFact>(|emit| {
            placed.extend(site_records::pass(
                table,
                pending,
                imports,
                cited,
                Pass::References(&mut *emit),
            ));
            for effect in &pending.script.effects {
                emit(&effect_record(cited, effect));
            }
        })?;
        // Python makes the bindings of the calls and the references in one pass over the sites.
        placed.sort_by_key(|(at, _)| *at);
        head.extend(placed.into_iter().map(|(_, record)| record));
        let bindings = head;
        sink.write_typed_section::<BindingFact>(|emit| bindings.iter().for_each(emit))?;
        constructs(pending, cited, expanded);
        sink.write_typed_section::<ConstructFact>(|emit| {
            expanded.constructs.iter().for_each(emit)
        })?;
        let (evidence, touched) = self.cited.finish();
        let tail = Tail {
            measures: None,
            selected_files: self.selected_files,
            files_read: self.files_read,
            gaps: self.gaps,
            evidence,
        };
        Ok((tail, touched))
    }
}

/// The sections that the capability declares, in the order that the reply writes them.
fn sections() -> Vec<&'static str> {
    vec![
        ImportFact::section_name(),
        archkeel_facts::GapFact::section_name(),
        SymbolFact::section_name(),
        CallFact::section_name(),
        ReferenceFact::section_name(),
        BindingFact::section_name(),
        ConstructFact::section_name(),
    ]
}

/// The reply of the facts of a request, written into `out` (a compressed 8.0.0 or 9.0.0 reply).
pub(crate) fn write_reply(
    version: Version,
    facts: Facts,
    pending: &Pending,
    out: impl Write,
) -> Result<(), String> {
    let (head, plan) = plan(facts, pending, false);
    encode_stream(version, head, out, |writer| {
        plan.write(writer).map(|(tail, _)| tail)
    })
}

/// The typed reply of the facts of a request (AD-406): the same plan and the same sections as
/// `write_reply`, given to the typed sink of the wire instead of the compressor.
pub(crate) fn typed_reply(
    version: Version,
    facts: Facts,
    pending: &Pending,
) -> Result<archkeel_facts::envelope::Reply, String> {
    let (head, plan) = plan(facts, pending, false);
    let mut reply = archkeel_wire::typed::assemble(version, head, |sink| {
        plan.write(sink).map(|(tail, _)| tail)
    })?;
    use archkeel_facts::envelope::{LimitSupport, ProfileLimits};
    reply.facts.scope_premise = Some(if pending.script.generated_copies {
        SCRIPT_PREMISE_GENERATED
    } else {
        SCRIPT_PREMISE
    });
    reply.facts.profile_limits = Some(ProfileLimits {
        dependency_symbols: if reply
            .facts
            .capabilities
            .resolution_features
            .iter()
            .any(|feature| feature == "script-globals-v1")
        {
            LimitSupport::Supported
        } else {
            LimitSupport::Unsupported
        },
        interface_boundary: LimitSupport::Supported,
        publication_surface: LimitSupport::Unsupported,
    });
    Ok(reply)
}

#[cfg(test)]
#[path = "records_tests.rs"]
mod tests;
