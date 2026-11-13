// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The gaps between two modules (#953, AD-357) and the rules that each gap can change (slice
//! S7, AD-384).
//!
//! A pair gap `a -> b` says: the collector cannot tell whether `a` uses `b`. The host drops it
//! when the contract allows the edge (`check/pair_gaps.py` `drop_allowed_pair_gaps`); this file
//! ports that rule with its cycle part, so a gap that it drops is `dropped` and a gap that it
//! keeps is `kept`. A dropped gap holds the rules whose reading it can change
//! (`dropped_gaps.rs`, AD-NNN). The reference engine then makes every rule UNKNOWN for a kept gap. The core
//! makes UNKNOWN only the rules whose reading (`Reads`) the gap can change: this is the one place
//! where the core decides a rule that the reference engine does not decide (AD-384 point 4).
//!
//! A gap is a proven pair only when both ends are modules of the reply. Any other gap holds
//! every rule, because it can stand for a module that the scan did not see.

use std::collections::{BTreeSet, HashMap, HashSet, VecDeque};

use archkeel_facts::envelope::PairGapDrop;

use archkeel_contract::{kind_of, Component, Contract, CycleLevel, Rule, RuleKind};

use crate::graph::Graph;
use crate::ids::{ComponentId, Table};
use crate::imports::Resolved;
use crate::ownership::{in_scope, owner_of};
use crate::selection::{dependency_sides, Selection};

/// One pair gap and the facts of its two ends that a reading needs.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) struct PairGap {
    pub(crate) source: String,
    pub(crate) target: String,
    /// Both ends are modules of the reply.
    pub(crate) observed: bool,
    /// The one owner of each end, or `None` for zero or many.
    pub(crate) owned: [bool; 2],
    /// The target module imports an external package: it can re-export it.
    pub(crate) target_external: bool,
}

/// The pair gaps of a run, classified one time per model.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub(crate) struct Pairs {
    pub(crate) kept: Vec<PairGap>,
    /// The gaps that the drop rule drops for a profile whose host drops them. The drop rule reads
    /// the selector texts, not the sides of a rule (AD-384 point 4), so a dropped gap still holds
    /// each rule whose reading it can change (`dropped_gaps.rs`, AD-NNN).
    pub(crate) dropped: Vec<PairGap>,
}

/// What a rule reads of the import edges between two modules. A rule kind states its reading;
/// a kept gap holds the rule only when it can change that reading.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Reads<'r> {
    /// No edge between two modules: the layout, the layers, the symbols and a permission.
    NoEdge,
    /// The set of modules only (`complete_assignment`): an edge adds no module.
    Modules,
    /// The direct external imports of each module. An internal edge adds none, but the target
    /// module can re-export an external package, so a gap into such a module holds the rule.
    ExternalImports,
    /// The edges from the source side to the target side (`forbidden_dependency`). An end that
    /// no one component owns can be on either side.
    Sides([Selection<'r>; 2]),
    /// The edges that touch a member scope (`sibling_isolation`).
    Members(Vec<&'r str>),
    /// Every edge.
    Every,
}

/// The reading of a rule. Each kind has an arm; a kind without a proof of a narrower reading
/// reads every edge.
pub fn reads<'r>(rule: &'r Rule, components: &'r [Component]) -> Reads<'r> {
    match rule {
        Rule::ForbiddenDependency(rule) => Reads::Sides(dependency_sides(rule, components)),
        Rule::SiblingIsolation(rule) => {
            Reads::Members(rule.members().iter().map(|m| m.as_text()).collect())
        }
        other => by_kind(kind_of(other)),
    }
}

/// The reading of a kind that needs no field of its rule.
fn by_kind(kind: RuleKind) -> Reads<'static> {
    use RuleKind as K;
    match kind {
        K::RootLayout | K::LayerOrder | K::SymbolPlacement | K::AllowedDependency => Reads::NoEdge,
        K::CompleteAssignment => Reads::Modules,
        K::ExternalDependencyScope | K::CompleteExternalScope => Reads::ExternalImports,
        // `reads` gives these two their own reading; here they read every edge (fail closed).
        K::ForbiddenDependency | K::SiblingIsolation => Reads::Every,
        K::CompleteRequires
        | K::NoComponentCycles
        | K::InterfaceBoundary
        | K::ForbiddenConstruct
        | K::SourceOwnership
        | K::BoundedNumericOperand
        | K::CallOwner
        | K::ForbiddenCallArgument
        | K::CatalogArgument
        | K::CatalogUse
        | K::ForbiddenEffectUnderCondition
        | K::ProtocolDeclarations
        | K::BoundaryTypes => Reads::Every,
    }
}

impl PairGap {
    /// True when the gap can change what the rule reads.
    pub(crate) fn holds(&self, reads: &Reads<'_>) -> bool {
        if !self.observed {
            return true;
        }
        let (a, b) = (self.source.as_str(), self.target.as_str());
        match reads {
            Reads::NoEdge | Reads::Modules => false,
            Reads::ExternalImports => self.target_external,
            Reads::Sides([sources, targets]) => {
                (sources.matches(a) || !self.owned[0]) && (targets.matches(b) || !self.owned[1])
            }
            Reads::Members(members) => members
                .iter()
                .any(|member| in_scope(a, member) || in_scope(b, member)),
            Reads::Every => true,
        }
    }
}

/// The pair gaps of a run: the drop rule of the host decides which it keeps.
pub(crate) fn pairs(
    contract: &Contract,
    components: &Table<ComponentId, Component>,
    graph: &Graph,
) -> Pairs {
    let gaps = &graph.observed().pair_gaps;
    if gaps.is_empty() {
        return Pairs::default();
    }
    let modules: HashSet<&str> = graph.modules().iter().map(|(_, m)| m.name()).collect();
    let external: HashSet<&str> = graph
        .imports()
        .iter()
        .filter(|import| matches!(import.resolved, Resolved::External(_)))
        .map(|import| import.source_module())
        .collect();
    let owner = |module: &str| owner_of(components, module);
    let cyclic = Cyclic::of(contract, components, graph, gaps);
    // `drop_allowed_pair_gaps` drops only for a profile whose host drops (`pair_gaps.py:66`).
    let drops = graph.observed().pair_gap_drop == PairGapDrop::Allowed;
    let mut found = Pairs::default();
    for (source, target) in gaps {
        let ends = [owner(source), owner(target)];
        let dropped = match ends {
            [Some(from), Some(to)] if drops => {
                let (from_row, to_row) = (components.get(from), components.get(to));
                let crossing = from_row
                    .zip(to_row)
                    .is_some_and(|(f, t)| requires_plainly(f, t));
                !named(contract, [source, target])
                    && !cyclic.module.contains(&(source.as_str(), target.as_str()))
                    && (from == to || (crossing && !cyclic.component.contains(&(from, to))))
            }
            _ => false,
        };
        let gap = PairGap {
            source: source.clone(),
            target: target.clone(),
            observed: modules.contains(source.as_str()) && modules.contains(target.as_str()),
            owned: ends.map(|end| end.is_some()),
            target_external: external.contains(target.as_str()),
        };
        if dropped {
            found.dropped.push(gap);
        } else {
            found.kept.push(gap);
        }
    }
    found
}

/// The pairs `(x, y)` of each active cycle level where `y` reaches `x`: with the edge `x -> y`,
/// one cycle group (`_cyclic`).
struct Cyclic<'g> {
    module: HashSet<(&'g str, &'g str)>,
    component: HashSet<(ComponentId, ComponentId)>,
}

impl<'g> Cyclic<'g> {
    fn of(
        contract: &Contract,
        components: &Table<ComponentId, Component>,
        graph: &'g Graph,
        gaps: &'g [(String, String)],
    ) -> Self {
        let levels: Vec<&CycleLevel> = contract
            .rules()
            .iter()
            .filter_map(|rule| match rule {
                Rule::NoComponentCycles(rule) => Some(rule.level()),
                _ => None,
            })
            .collect();
        let mut edges: BTreeSet<(&'g str, &'g str)> = graph
            .imports()
            .iter()
            .map(|import| (import.source_module(), import.target_module()))
            .collect();
        edges.extend(gaps.iter().map(|(a, b)| (a.as_str(), b.as_str())));
        let mut module = HashSet::new();
        if levels.contains(&&CycleLevel::Module) {
            let starts = gaps.iter().map(|(_, b)| b.as_str()).collect();
            module = reach(&edges, &starts);
        }
        let mut component = HashSet::new();
        if levels.iter().any(|level| **level != CycleLevel::Module) {
            let owner = |module: &str| owner_of(components, module);
            let parts: BTreeSet<(ComponentId, ComponentId)> = edges
                .iter()
                .filter_map(|(s, t)| Some((owner(s)?, owner(t)?)))
                .collect();
            let starts = gaps.iter().filter_map(|(_, b)| owner(b)).collect();
            component = reach(&parts, &starts);
        }
        Cyclic { module, component }
    }
}

/// Each `(x, start)` where `start` reaches `x` in one or more steps. The walk is a queue, so no
/// depth reaches the call stack.
fn reach<N: Copy + Eq + std::hash::Hash + Ord>(
    edges: &BTreeSet<(N, N)>,
    starts: &BTreeSet<N>,
) -> HashSet<(N, N)> {
    let mut successors: HashMap<N, Vec<N>> = HashMap::new();
    for &(source, target) in edges {
        successors.entry(source).or_default().push(target);
    }
    let mut found = HashSet::new();
    for &start in starts {
        let mut seen: HashSet<N> = HashSet::new();
        let mut queue: VecDeque<N> = successors
            .get(&start)
            .into_iter()
            .flatten()
            .copied()
            .collect();
        while let Some(node) = queue.pop_front() {
            if seen.insert(node) {
                queue.extend(successors.get(&node).into_iter().flatten().copied());
            }
        }
        found.extend(seen.into_iter().map(|node| (node, start)));
    }
    found
}

/// True when `from` requires `to` with an entry without `through`.
fn requires_plainly(from: &Component, to: &Component) -> bool {
    from.requires()
        .iter()
        .flatten()
        .any(|required| required.component() == to.label() && required.through().is_empty())
}

/// `_named`: a rule names an end by a selector field, or the rule is of a kind that the drop
/// rule does not know.
fn named(contract: &Contract, ends: [&String; 2]) -> bool {
    contract.rules().iter().any(|rule| {
        let names: Vec<&str> = match rule {
            Rule::ForbiddenDependency(rule) => [rule.source(), rule.target()]
                .into_iter()
                .chain(rule.allowed_sources())
                .map(|s| s.as_text())
                .collect(),
            Rule::AllowedDependency(rule) => vec![rule.source().as_text(), rule.target().as_text()],
            Rule::SiblingIsolation(rule) => rule.members().iter().map(|s| s.as_text()).collect(),
            other => return !EDGE_FREE.contains(&archkeel_contract::kind_of(other)),
        };
        names.iter().any(|name| {
            ends.iter()
                .any(|end| in_scope(end, name) || in_scope(name, end))
        })
    })
}

/// The kinds that the drop rule of the host knows as free of edges (`_EDGE_FREE`).
const EDGE_FREE: &[RuleKind] = &[
    RuleKind::CompleteAssignment,
    RuleKind::CompleteExternalScope,
    RuleKind::CompleteRequires,
    RuleKind::ExternalDependencyScope,
    RuleKind::ForbiddenConstruct,
    RuleKind::RootLayout,
    RuleKind::NoComponentCycles,
];

#[cfg(test)]
#[path = "pair_gaps_tests.rs"]
mod tests;
