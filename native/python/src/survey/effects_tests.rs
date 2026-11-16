// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the model holds with a gap only the rules that read its effect (AD-564). A too
// narrow effect is a false PASS, so each kind of site has its row, and a kind without a row has
// no effect.

use archkeel_facts::data::GapEffect;
use archkeel_facts::ids::ModuleName;
use archkeel_facts::Record;

use super::{of, AMBIGUOUS, BEYOND_TOP, NOT_FOUND, STAR};
use crate::survey::targets::tests::{reason, surveyed};
use crate::survey::Survey;
use crate::survey::{hazards, layout, syspath, targets};

const CLIENT: &str = "app.client";

fn code_of(module: &str) -> Option<GapEffect> {
    Some(GapEffect::Modules {
        modules: vec![ModuleName::new(module)],
    })
}

#[test]
fn each_kind_of_site_states_its_effect_and_an_unnamed_kind_states_none() {
    let rows = [
        (hazards::DYNAMIC, Some(GapEffect::EveryModule)),
        (hazards::IMPORT_SYSTEM, Some(GapEffect::EveryModule)),
        (STAR, code_of(CLIENT)),
        (AMBIGUOUS, code_of(CLIENT)),
        (BEYOND_TOP, Some(GapEffect::EveryModule)),
        (NOT_FOUND, Some(GapEffect::EveryModule)),
        (hazards::LITERAL, None),
        (syspath::PATH_WRITE, None),
        (layout::OUTSIDE_LAYOUT, None),
        (layout::DUPLICATE, None),
        ("a_new_kind", None),
    ];
    for (kind, expected) in rows {
        assert_eq!(of(kind, CLIENT), expected, "{kind}");
    }
}

/// The reason and the effect of each gap of the survey of `src/app/client.py` with `source`.
fn effects(source: &str, init: &str) -> Vec<(String, Option<GapEffect>)> {
    let found: Survey = surveyed(&[
        ("src/app/__init__.py", init),
        ("src/app/client.py", source),
        ("src/app/service.py", ""),
    ]);
    let effect = |gap: &Record<archkeel_facts::GapFact>| gap.data.data().effect.clone();
    let rows = found.unknowns.iter();
    rows.map(|gap| (reason(gap), effect(gap))).collect()
}

#[test]
fn the_gap_of_each_site_of_a_survey_carries_the_effect_of_its_kind() {
    let every = Some(GapEffect::EveryModule);
    for (source, init, kind, expected) in [
        ("exec(open('x').read())\n", "", hazards::DYNAMIC, &every),
        (
            "import importlib\nimportlib.import_module(name)\n",
            "",
            hazards::DYNAMIC,
            &every,
        ),
        (
            "import pickle\npickle.loads(data)\n",
            "",
            hazards::DYNAMIC,
            &every,
        ),
        (
            "import sys\nsys.path.insert(0, 'x')\n",
            "",
            hazards::IMPORT_SYSTEM,
            &every,
        ),
        ("from app import *\n", "", STAR, &code_of(CLIENT)),
        (
            "from app import service\n",
            "service = 1\n",
            AMBIGUOUS,
            &code_of(CLIENT),
        ),
        ("import app.missing\n", "", NOT_FOUND, &every),
        ("from ... import other\n", "", BEYOND_TOP, &every),
    ] {
        let found = effects(source, init);
        let of_kind: Vec<_> = found
            .iter()
            .filter(|(reason, _)| reason.starts_with(kind))
            .collect();
        assert!(!of_kind.is_empty(), "{source}: {found:?}");
        for (reason, effect) in of_kind {
            assert_eq!(effect, expected, "{source}: {reason}");
        }
    }
}

#[test]
fn the_effect_is_no_part_of_the_id_of_a_gap() {
    let (id, record) = targets::site_gap(STAR, "app", CLIENT, "EVIDENCE-1");
    let reason = format!("{}: app", STAR);
    let gap = archkeel_facts::GapFact::resolution(&reason, CLIENT);
    let (plain, without) = Record::unknown_gap(&reason, Some("EVIDENCE-1"), CLIENT, gap);
    assert_eq!(id, plain);
    assert_eq!(record.data.data().effect, code_of(CLIENT));
    assert_eq!(without.data.data().effect, None);
}
