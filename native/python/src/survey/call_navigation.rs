// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Source navigation can match a written name even when mutation prevents a runtime proof.

use std::collections::{HashMap, HashSet};

use archkeel_facts::envelope::{SourceCallCandidate, Target};
use archkeel_facts::ids::{EvidenceId, ModuleName};
use archkeel_facts::{vocab::Status, CallFact, ImportFact, Record};
use ruff_python_ast::helpers::any_over_body;
use ruff_python_ast::{Expr, ExprCall, Identifier, Stmt, StmtClassDef};
use ruff_text_size::Ranged;

use super::binders::Binders;
use super::bound::Bound;
use super::declared::{self, scope::Uses};
use crate::module::{EvidenceMap, Module};

type Declarations<'m> = HashMap<(&'m str, &'m str), (&'m Module, &'m Identifier)>;

pub(super) fn collect(
    modules: &[Module],
    binders: &[Binders],
    imports: &[Record<ImportFact>],
    targets: &[Target],
    calls: &[Record<CallFact>],
    evidence: &mut EvidenceMap,
) -> Vec<SourceCallCandidate> {
    let mut definitions = Declarations::new();
    let mut visible: HashMap<&str, _> = HashMap::new();
    for (module, binders) in modules.iter().zip(binders) {
        let unique = binders.unique();
        for stmt in &module.tree.body {
            let name = match stmt {
                Stmt::FunctionDef(node) => &node.name,
                Stmt::ClassDef(node) => &node.name,
                _ => continue,
            };
            if unique.contains(name.as_ref()) {
                definitions.insert((&module.name, name.as_ref()), (module, name));
            }
        }
        visible.insert(&module.name, unique);
    }
    let local: HashMap<_, _> = targets
        .iter()
        .filter_map(|target| match target {
            Target::Local {
                import_id, module, ..
            } => Some((import_id, module)),
            _ => None,
        })
        .collect();
    let mut bindings = Bindings::new();
    for item in imports {
        let ImportFact::Import(data) = &item.data else {
            continue;
        };
        let (Some(bound), Some(symbol)) = (&data.binding, &data.symbol) else {
            continue;
        };
        let source = ModuleName::as_str(&data.source_module);
        let provider = ModuleName::as_str(&data.target_module);
        if data.module_level_import
            && !data.under_type_checking
            && local.get(&item.id) == Some(&&data.target_module)
            && visible
                .get(source)
                .is_some_and(|names| names.contains(bound))
        {
            bindings.insert((source, bound), (provider, symbol));
        }
    }
    let mut candidates = Vec::new();
    for module in modules {
        let mut walk = Calls {
            module,
            definitions: &definitions,
            imports: &bindings,
            evidence,
            candidates: &mut candidates,
        };
        walk.names();
        for statement in &module.tree.body {
            let Stmt::ClassDef(class) = statement else {
                continue;
            };
            if definitions.contains_key(&(&module.name, class.name.as_ref())) {
                walk.methods(class);
            }
        }
    }
    let proven: HashSet<_> = calls
        .iter()
        .filter_map(|record| {
            let CallFact::Calls(data) = &record.data else {
                return None;
            };
            let [target] = &data.targets[..] else {
                return None;
            };
            (data.status == Status::Resolved).then_some((record.evidence_ids.first()?, target))
        })
        .collect();
    candidates.retain(|c| !proven.contains(&(&c.call_evidence, &c.target)));
    candidates
}

type Bindings<'m> = HashMap<(&'m str, &'m str), (&'m str, &'m str)>;

struct Calls<'m, 'a> {
    module: &'m Module,
    definitions: &'a Declarations<'m>,
    imports: &'a Bindings<'m>,
    evidence: &'a mut EvidenceMap,
    candidates: &'a mut Vec<SourceCallCandidate>,
}

impl Calls<'_, '_> {
    fn names(&mut self) {
        any_over_body(&self.module.tree.body, |expr| {
            let Expr::Call(call) = expr else { return false };
            if let Expr::Name(name) = &*call.func {
                self.name(call, name);
            }
            false
        });
    }

    fn name(&mut self, call: &ExprCall, node: &ruff_python_ast::ExprName) {
        let name: &str = &node.id;
        if name.starts_with("__") && !name.ends_with("__") {
            return;
        }
        let own: (&str, &str) = (&self.module.name, name);
        let (provider, symbol) = self.imports.get(&own).copied().unwrap_or(own);
        let Some(&(target_module, declaration)) = self.definitions.get(&(provider, symbol)) else {
            return;
        };
        self.emit(
            call,
            name.to_owned(),
            target_module,
            format!("{provider}.{symbol}"),
            declaration,
        );
    }

    fn methods(&mut self, class: &StmtClassDef) {
        if !matches!(&class.decorator_list[..], [])
            || class
                .arguments
                .as_ref()
                .is_some_and(|args| !matches!(&args.keywords[..], []))
        {
            return;
        }
        let bound = Bound::of(&class.body);
        let methods: HashMap<&str, _> = class
            .body
            .iter()
            .filter_map(|stmt| match stmt {
                Stmt::FunctionDef(method)
                    if matches!(&method.decorator_list[..], [])
                        && bound.sole(method.name.as_ref(), method.start()) =>
                {
                    Some((method.name.as_ref(), method))
                }
                _ => None,
            })
            .collect();
        // Walk in source order even when method lookup uses a hash table.
        for stmt in &class.body {
            let Stmt::FunctionDef(method) = stmt else {
                continue;
            };
            if !methods.contains_key(method.name.as_ref()) {
                continue;
            }
            let Some(receiver) = declared::receiver(method) else {
                continue;
            };
            self.method_calls(class, &receiver, Uses::of(method), &methods);
        }
    }

    fn method_calls(
        &mut self,
        class: &StmtClassDef,
        receiver: &str,
        uses: Uses<'_>,
        methods: &HashMap<&str, &ruff_python_ast::StmtFunctionDef>,
    ) {
        for (call, dead) in uses.calls {
            let Expr::Attribute(attr) = &*call.func else {
                continue;
            };
            if dead || !matches!(&*attr.value, Expr::Name(name) if name.id == receiver) {
                continue;
            }
            let Some(target) = methods.get(attr.attr.as_ref()) else {
                continue;
            };
            let expression = format!("{receiver}.{}", attr.attr);
            let qualified = format!("{}.{}.{}", self.module.name, class.name, target.name);
            self.emit(call, expression, self.module, qualified, &target.name);
        }
    }

    fn emit(
        &mut self,
        call: &ExprCall,
        expression: String,
        target_module: &Module,
        target: String,
        declaration: &Identifier,
    ) {
        self.candidates.push(SourceCallCandidate {
            source_module: self.module.name.clone(),
            target_module: target_module.name.clone(),
            target,
            expression,
            call_evidence: EvidenceId::new(self.module.evidence(self.evidence, call)),
            declaration_evidence: EvidenceId::new(
                target_module.evidence(self.evidence, declaration),
            ),
        });
    }
}

#[cfg(test)]
mod tests {
    use crate::survey::targets::tests::survey_of;
    use archkeel_snapshot::test_tree::Tree;

    #[test]
    fn written_bindings_cite_both_locations_without_deciding_the_verdict() {
        let tree = Tree::new(&[
            ("src/pkg/__init__.py", ""),
            ("src/pkg/api.py", "class Output: pass\ndef parse(): pass\n"),
            ("src/pkg/client.py", "from .api import Output as Result\nfrom .api import parse\ndef helper(): pass\ndef run():\n    helper(); Result()\n    parse(); parse()\neval(payload)\n"),
            ("src/pkg/clean.py", "def target(): pass\ndef caller(): return target()\n"),
            ("src/pkg/shadow.py", "from .api import parse\ndef f(parse):\n    parse()\n"),
            ("src/pkg/other.py", "from .api import Output as Result\nResult = fake\nResult()\n"),
            ("src/pkg/dynamic.py", "import json\njson.loads('0')\nclient.parse()\n"),
        ]);
        let plain = survey_of(&tree, &["src"], "pkg", false);
        let detailed = survey_of(&tree, &["src"], "pkg", true);
        assert_eq!(plain.coverage, detailed.coverage);
        assert_eq!(plain.sites.calls, detailed.sites.calls);
        assert!(plain.source_call_candidates.is_empty());
        let rows = &detailed.source_call_candidates;
        let names: Vec<_> = rows
            .iter()
            .map(|c| (c.expression.as_str(), c.target.as_str()))
            .collect();
        assert_eq!(
            names,
            [
                ("helper", "pkg.client.helper"),
                ("Result", "pkg.api.Output"),
                ("parse", "pkg.api.parse"),
                ("parse", "pkg.api.parse")
            ]
        );
        assert_ne!(rows[2].call_evidence, rows[3].call_evidence);
        for (id, file, line) in [
            (&rows[1].call_evidence, "src/pkg/client.py", 5),
            (&rows[1].declaration_evidence, "src/pkg/api.py", 1),
        ] {
            assert!(detailed
                .evidence
                .iter()
                .any(|e| &e.id == id && e.file == file && e.line == line));
        }
    }
}

#[cfg(test)]
#[test]
fn receiver_navigation_respects_scope_and_method_kind() {
    use crate::survey::targets::tests::survey_of;
    use archkeel_snapshot::test_tree::Tree;
    let tree = Tree::new(&[(
        "src/pkg/ui.py",
        r"
class View:
    def draw(self): pass
    def run(this):
        this.draw()
        def inner(this):
            this.draw()
        return lambda this: this.draw()
    def replaced(self):
        self = another()
        self.draw()
    @staticmethod
    def utility(self):
        self.draw()
    @classmethod
    def construct(cls):
        cls.draw()
    def unknown(self):
        self.external()
        self.utility()
",
    )]);
    let found = survey_of(&tree, &["src"], "pkg", true);
    let rows = found.source_call_candidates;
    assert_eq!(rows.len(), 1);
    assert_eq!(
        (&*rows[0].expression, &*rows[0].target),
        ("this.draw", "pkg.ui.View.draw")
    );
}
