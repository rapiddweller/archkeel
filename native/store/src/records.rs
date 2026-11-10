// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The record checks of `validate_source_facts` (AD-346): unique ids, dangling evidence and fact
//! references, the evidence class of each section, the construct capabilities, the member
//! inventories, the base declarations, the coverage gaps and the typed import targets.
//!
//! One pass reads each typed record through its `View` and keeps only small indexes. A field
//! that needs a Python source proof (`call_binding`, `numeric_operand`, ...) is refused: the store
//! does not check that proof, so it must not pass it on.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::{ConstructSupport, Facts, Profile};
use archkeel_facts::vocab::{EvidenceClass, InventoryStatus, MemberKind, Status};
use archkeel_facts::{FactData, Record, Section};

use crate::bindings::Modules;
use crate::stored::{visit, Visitor};
use crate::validate::{unique, Envelope};
use crate::view::View;

/// Kinds whose proof is a Python check that the store does not port yet.
const UNCHECKED_KINDS: [&str; 5] = [
    "numeric_operand",
    "construct_selector",
    "source_role",
    "value_reference",
    "attribute_reference",
];

/// One member inventory receipt: its class, its kind, its ids and the attribute ids of the class.
struct Inventory {
    owner: String,
    kind: MemberKind,
    declared: HashSet<String>,
    attributes: Option<Vec<String>>,
}

/// The small indexes that the checks across records need.
struct Pass<'a> {
    facts: &'a Facts,
    envelope: &'a Envelope<'a>,
    modules: Modules<'a>,
    section: usize,
    position: usize,
    places: HashMap<String, (usize, usize)>,
    fact_refs: Vec<String>,
    methods: HashMap<String, HashSet<String>>,
    inventories: Vec<Inventory>,
    imports: HashMap<String, (Option<String>, Option<String>)>,
    effects: bool,
}

fn envelope_class(section: &Section, class: EvidenceClass) -> Result<(), String> {
    let unknowns = matches!(section, Section::Unknowns(_));
    match (unknowns, class) {
        (true, EvidenceClass::Unknown) | (false, EvidenceClass::Fact) => Ok(()),
        (true, _) => Err("source unknowns must be UNKNOWN".to_owned()),
        (false, _) => Err("measured source sections must contain FACT records".to_owned()),
    }
}

fn base_declarations(view: &View<'_>, section: &Section) -> Result<(), String> {
    let Some(bases) = view.data.base_declarations else {
        return Ok(());
    };
    if !matches!(section, Section::Symbols(_)) || view.kind != "class" {
        return Err("base declarations need a class symbol and typed base records".to_owned());
    }
    for base in bases {
        let count = base.candidate_count;
        let length = i64::try_from(base.targets.len()).unwrap_or(i64::MAX);
        let truncated = base.candidates_truncated.unwrap_or(false);
        let invalid = base.id.as_str().is_empty()
            || base.expression.is_empty()
            || base.targets.iter().any(String::is_empty)
            || count < length
            || (base.status == Status::Resolved && base.targets.len() != 1)
            || (base.status == Status::Unresolved && !base.targets.is_empty())
            || base.status == Status::Decided
            || (truncated && (base.status != Status::PartiallyResolved || count <= length))
            || base.evidence_ids.iter().any(|id| id.as_str().is_empty());
        if invalid {
            return Err("invalid typed base declaration".to_owned());
        }
    }
    Ok(())
}

impl Pass<'_> {
    fn construct(&self, view: &View<'_>) -> Result<(), String> {
        let Some(name) = view.data.construct else {
            return Ok(());
        };
        let declared = self
            .facts
            .capabilities
            .constructs
            .iter()
            .any(|entry| entry.name == name && entry.status != ConstructSupport::Unsupported);
        if declared {
            Ok(())
        } else {
            Err("source construct disagrees with declared capabilities".to_owned())
        }
    }

    fn index(&mut self, view: &View<'_>, section: &Section) -> Result<(), String> {
        let place = (self.section, self.position);
        if self.places.insert(view.id.to_owned(), place).is_some() {
            return Err("duplicate source record id".to_owned());
        }
        if view.id.is_empty() {
            return Err("empty source record id".to_owned());
        }
        if self.envelope.file_ids.contains(view.id) {
            return Err("file and record ids collide".to_owned());
        }
        self.fact_refs
            .extend(view.fact_ids.iter().map(|id| id.as_str().to_owned()));
        self.effects |= view.kind == "script_namespace_effect";
        if view.kind == "method" {
            if let Some(parent) = view.data.lexical_parent_id {
                let methods = self.methods.entry(parent.to_owned()).or_default();
                methods.insert(view.id.to_owned());
            }
        }
        if let Some(inventories) = view.data.member_inventories {
            if !matches!(section, Section::Symbols(_)) || view.kind != "class" {
                return Err("member inventory needs its class owner".to_owned());
            }
            let attributes = view.data.attribute_declarations.map(|items| {
                items
                    .iter()
                    .map(|item| item.definition_id.as_str().to_owned())
                    .collect()
            });
            if inventories
                .iter()
                .any(|item| item.schema_version != "1.0.0")
            {
                return Err("unsupported member inventory version".to_owned());
            }
            for inventory in inventories {
                let ids = inventory
                    .definition_ids
                    .iter()
                    .map(|id| id.as_str().to_owned());
                self.inventories.push(Inventory {
                    owner: view.id.to_owned(),
                    kind: inventory.kind,
                    declared: ids.collect(),
                    attributes: attributes.clone(),
                });
            }
            let kinds: HashSet<MemberKind> = inventories.iter().map(|item| item.kind).collect();
            let statuses = inventories.iter().all(|item| {
                matches!(
                    item.status,
                    InventoryStatus::Complete | InventoryStatus::Partial
                )
            });
            if inventories.len() != 2 || kinds.len() != 2 || !statuses {
                return Err("member inventory needs one receipt per member kind".to_owned());
            }
        }
        if matches!(section, Section::Imports(_)) {
            let fields = (
                view.data.target_module.map(str::to_owned),
                view.data.target_package.map(str::to_owned),
            );
            self.imports.insert(view.id.to_owned(), fields);
        }
        Ok(())
    }
}

impl Visitor for Pass<'_> {
    fn record<D: FactData>(&mut self, section: &Section, record: &Record<D>) -> Result<(), String> {
        let view = View::new(record);
        if !view
            .evidence_ids
            .iter()
            .all(|id| self.envelope.evidence_ids.contains(id.as_str()))
        {
            return Err("dangling source evidence reference".to_owned());
        }
        envelope_class(section, view.evidence_class)?;
        if UNCHECKED_KINDS.contains(&view.kind) {
            return Err(format!(
                "the store does not check {} records yet",
                view.kind
            ));
        }
        if let Some(field) = view.unchecked() {
            return Err(format!("the store does not check the field {field} yet"));
        }
        self.construct(&view)?;
        base_declarations(&view, section)?;
        self.index(&view, section)?;
        if !matches!(section, Section::Unknowns(_)) {
            let imports = matches!(section, Section::Imports(_));
            self.modules
                .bind(&view, imports, &self.envelope.selected_inputs)?;
        }
        self.position += 1;
        Ok(())
    }
}

impl Pass<'_> {
    fn member_inventories(&self) -> Result<(), String> {
        for Inventory {
            owner,
            kind,
            declared,
            attributes,
        } in &self.inventories
        {
            let actual = match kind {
                MemberKind::Method => self.methods.get(owner).cloned().unwrap_or_default(),
                MemberKind::Attribute => {
                    let ids = attributes.as_ref().ok_or(
                        "member inventory needs explicit attribute declarations".to_owned(),
                    )?;
                    let set = unique(ids.iter().map(String::as_str), "member inventory attribute")?;
                    set.into_iter().map(str::to_owned).collect()
                }
            };
            if &actual != declared {
                return Err("member inventory identities disagree with their owner".to_owned());
            }
        }
        Ok(())
    }

    fn gaps(&self, sections: &[Section]) -> Result<(), String> {
        for gap in &self.facts.coverage.gaps {
            let view = View::new(gap);
            envelope_class(&Section::Unknowns(Vec::new()), view.evidence_class)?;
            let place = self.places.get(gap.id.as_str());
            let same = place.is_some_and(|(section, index)| match &sections[*section] {
                Section::Unknowns(records) => records.get(*index) == Some(gap),
                _ => false,
            });
            if !same {
                return Err("coverage gap must reference its source UNKNOWN record".to_owned());
            }
            let effects = self.facts.profile == Profile::TypeScript
                && self.envelope.features.contains("script-globals-v1");
            self.modules
                .effect_gap(&view, sections, &self.places, effects)?;
        }
        Ok(())
    }

    fn import_targets(&self) -> Result<(), String> {
        let ids = self
            .facts
            .imports
            .iter()
            .map(|target| target.import_id().as_str());
        let targets = unique(ids, "import target")?;
        let imports: HashSet<&str> = self.imports.keys().map(String::as_str).collect();
        if targets != imports {
            return Err("each import needs exactly one typed target".to_owned());
        }
        for target in &self.facts.imports {
            let (module, package) = &self.imports[target.import_id().as_str()];
            self.modules.target(
                target,
                module.as_deref(),
                package.as_deref(),
                self.facts.coverage.full_scope,
                &self.envelope.inputs,
            )?;
        }
        Ok(())
    }
}

/// The record checks. The result maps each record id to its section and position.
pub(crate) fn records(
    facts: &Facts,
    envelope: &Envelope<'_>,
) -> Result<HashMap<String, (usize, usize)>, String> {
    let mut pass = Pass {
        facts,
        envelope,
        modules: Modules::of(facts)?,
        section: 0,
        position: 0,
        places: HashMap::new(),
        fact_refs: Vec::new(),
        methods: HashMap::new(),
        inventories: Vec::new(),
        imports: HashMap::new(),
        effects: false,
    };
    for (index, section) in facts.sections.iter().enumerate() {
        (pass.section, pass.position) = (index, 0);
        visit(section, 0, section.len(), &mut pass)?;
    }
    let known =
        |id: &String| pass.places.contains_key(id) || envelope.file_ids.contains(id.as_str());
    if !pass.fact_refs.iter().all(known) {
        return Err("dangling source fact reference".to_owned());
    }
    let script =
        facts.profile == Profile::TypeScript && envelope.features.contains("script-globals-v1");
    if pass.effects && !script {
        return Err("script effects require the registered TypeScript script profile".to_owned());
    }
    pass.member_inventories()?;
    pass.gaps(&facts.sections)?;
    pass.import_targets()?;
    Ok(pass.places)
}
