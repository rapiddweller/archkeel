// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The imports expanded to one record for each bound name, and the export witness that proves a
//! name (`_named_imports`, `_export_binding`).

use std::collections::{HashMap, HashSet};

use archkeel_facts::data::BindingData;
use archkeel_facts::envelope::Target;
use archkeel_facts::identity::{stable_id, Part};
use archkeel_facts::ids::{EvidenceId, FactId};
use archkeel_facts::vocab::{Area, EvidenceClass};
use archkeel_facts::{BindingFact, Record};

use crate::cited::Cited;
use crate::collected::{import_section, sorted, Facts, ImportRecord, Records};
use crate::import_bindings::ImportBinding;
use crate::kept::{Kept, Pending};
use crate::source::Span;

/// `_named_imports`.
pub(crate) fn expand(facts: &Facts, pending: &Pending, cited: &mut Cited, records: &mut Records) {
    let by_id: HashMap<&str, &ImportRecord> = import_section(facts)
        .iter()
        .map(|record| (record.id.as_str(), record))
        .collect();
    let mut seen = HashSet::new();
    for target in &facts.imports {
        let Some(item) = by_id.get(target.import_id().as_str()) else {
            continue;
        };
        let bindings = pending.sites.get(item.id.as_str()).and_then(|site| {
            let kept = pending.kept.get(&site.rel)?;
            let own: &[ImportBinding] = kept.bindings.get(&(site.line, site.column))?;
            Some((kept, own))
        });
        let Some((kept, own)) = bindings else {
            let mut record = (*item).clone();
            record.data.data_mut().symbols_known |= module_object(pending, item, target);
            records.imports.push(record);
            records.targets.push(target.clone());
            continue;
        };
        for (ordinal, binding) in (0_i64..).zip(own.iter()) {
            let bound_id = stable_id(
                "IMP_BINDING",
                &[Part::Text(item.id.as_str()), Part::Number(ordinal)],
            );
            let mut fact_ids = match known_witness(pending, kept, binding, target) {
                Some(witness) => vec![add_witness(cited, records, &mut seen, &witness)],
                None => Vec::new(),
            };
            let mut chain = Vec::new();
            for witness in type_witnesses(facts, pending, kept, binding, target) {
                chain.push(format!("{}.{}", witness.0, witness.2));
                fact_ids.push(add_witness(cited, records, &mut seen, &witness));
            }
            let mut record = bound_record(item, &bound_id, binding, target, fact_ids);
            if binding.type_only && !chain.is_empty() {
                record.data.data_mut().reexport_chain = Some(chain);
            }
            records.imports.push(record);
            records.targets.push(target.with_import_id(&bound_id));
        }
    }
}

/// The bounded route uses the resolver's exact file target, never a name search across modules.
fn type_witnesses<'a>(
    facts: &Facts,
    pending: &'a Pending,
    source: &Kept,
    binding: &ImportBinding,
    target: &Target,
) -> Vec<Witness<'a>> {
    if !binding.type_only
        || pending.partial
        || source.has_error
        || !binding.source_unique
        || binding.namespace
        || binding.aliased
        || binding.imported == "default"
        || source.type_exports.declared.contains(&binding.local)
    {
        return Vec::new();
    }
    let Target::Local { file, .. } = target else {
        return Vec::new();
    };
    let Some(destination) = pending.kept.get(file).filter(|k| !k.has_error) else {
        return Vec::new();
    };
    if let Some(witness) = direct_type(destination, file, &binding.imported) {
        return vec![witness];
    }
    let Some(hop) = destination
        .type_exports
        .hops
        .iter()
        .find(|h| h.name == binding.imported)
    else {
        return Vec::new();
    };
    let edge = pending.sites.iter().find(|(_, site)| {
        site.rel == *file && site.line == hop.export.line && site.column == hop.export.column
    });
    let Some((id, _)) = edge else {
        return Vec::new();
    };
    let Some(Target::Local { file: leaf, .. }) =
        facts.imports.iter().find(|t| t.import_id().as_str() == id)
    else {
        return Vec::new();
    };
    let Some(implementation) = pending.kept.get(leaf).filter(|k| !k.has_error) else {
        return Vec::new();
    };
    let Some(witness) = direct_type(implementation, leaf, &binding.imported) else {
        return Vec::new();
    };
    vec![
        (
            destination.module.clone(),
            file.clone(),
            binding.imported.clone(),
            (&hop.declaration, &hop.export),
        ),
        witness,
    ]
}

fn direct_type<'a>(kept: &'a Kept, file: &str, name: &str) -> Option<Witness<'a>> {
    let binding = kept.type_exports.direct.iter().find(|b| b.name == name)?;
    Some((
        kept.module.clone(),
        file.to_owned(),
        name.to_owned(),
        (&binding.declaration, &binding.export),
    ))
}

/// Only a static import without bindings proves a whole-module import.
fn module_object(pending: &Pending, item: &ImportRecord, target: &Target) -> bool {
    let Target::Local {
        file,
        runtime_file: Some(_),
        ..
    } = target
    else {
        return false;
    };
    let source = pending
        .sites
        .get(item.id.as_str())
        .and_then(|s| pending.kept.get(&s.rel));
    matches!(item.data, archkeel_facts::ImportFact::Import(_))
        && !item.data.data().under_type_checking
        && !pending.partial
        && source.is_some_and(|s| !s.has_error)
        && pending.kept.get(file).is_some_and(|d| !d.has_error)
}

/// Record the witness of a proven name once and give its id.
fn add_witness(
    cited: &mut Cited,
    records: &mut Records,
    seen: &mut HashSet<String>,
    witness: &Witness,
) -> String {
    let (module, file, name, spans) = witness;
    let id = stable_id("ESM_EXPORT", &[Part::Text(module), Part::Text(name)]);
    if seen.insert(id.clone()) {
        let record = export_record(cited, &id, module, file, name, spans);
        records.witnesses.push(record);
    }
    id
}

/// The witness of a name that is proven: `(module, file, name, (declaration, export))`.
type Witness<'a> = (String, String, String, (&'a Span, &'a Span));

/// `known` of `_named_imports`: the name resolves to one export of a file that has no error.
fn known_witness<'a>(
    pending: &'a Pending,
    kept: &Kept,
    binding: &ImportBinding,
    target: &Target,
) -> Option<Witness<'a>> {
    let Target::Local {
        module,
        file,
        runtime_file: Some(_),
        ..
    } = target
    else {
        return None;
    };
    let destination = pending.kept.get(file)?;
    let [(declaration, export)] = destination.exports.get(&binding.imported)?.as_slice() else {
        return None;
    };
    // Faithful copies of Python conditions that other conditions already imply: some of them are
    // equivalent mutants, so no test should try to kill them one by one.
    let proven = binding.source_unique
        && !binding.namespace
        && !binding.type_only
        && !kept.has_error
        && !pending.partial
        && !destination.has_error;
    proven.then(|| {
        (
            module.as_str().to_owned(),
            file.clone(),
            binding.imported.clone(),
            (declaration, export),
        )
    })
}

/// One expanded import record: the statement record with the bound name written into its data.
fn bound_record(
    item: &ImportRecord,
    id: &str,
    binding: &ImportBinding,
    target: &Target,
    fact_ids: Vec<String>,
) -> ImportRecord {
    let known = !fact_ids.is_empty();
    let chain = match target {
        Target::Local { module, .. } if known => {
            vec![format!("{}.{}", module.as_str(), binding.imported)]
        }
        _ => Vec::new(),
    };
    let mut record = item.clone();
    let data = record.data.data_mut();
    data.symbol = (!binding.namespace).then(|| binding.imported.clone());
    data.binding = Some(binding.local.clone());
    data.symbols_known = known;
    data.reexport_chain = Some(chain);
    data.type_only = Some(binding.type_only);
    data.under_type_checking = binding.type_only;
    record.id = FactId::new(id);
    record.fact_ids = fact_ids.into_iter().map(FactId::new).collect();
    record
}

/// `_export_binding`: the witness that a module exports a name once.
fn export_record(
    cited: &mut Cited,
    id: &str,
    module: &str,
    file: &str,
    name: &str,
    spans: &(&Span, &Span),
) -> Record<BindingFact> {
    let mut evidence_ids = vec![cited.cite(file, spans.0)];
    let export = cited.cite(file, spans.1);
    if !evidence_ids.contains(&export) {
        evidence_ids.push(export);
    }
    let data = BindingData {
        name: Some(name.to_owned()),
        ..BindingData::in_module(module)
    };
    Record {
        id: FactId::new(id),
        evidence_class: EvidenceClass::Fact,
        area: Area::Source,
        title: "Exported source binding".to_owned(),
        subjects: sorted(vec![module.to_owned()]),
        evidence_ids: sorted(evidence_ids)
            .into_iter()
            .map(EvidenceId::new)
            .collect(),
        fact_ids: Vec::new(),
        data: BindingFact::Bindings(data),
    }
}
