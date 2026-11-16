// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the effect of each Dart gap name (AD-564). A package gap leaves the edges of every
// library unknown; a site leaves its own library unknown; a gap that can move code or a file to
// a library that it does not name states no effect.

use archkeel_facts::data::GapEffect;
use archkeel_facts::ids::ModuleName;

use super::GapName;

#[test]
fn each_gap_name_states_the_effect_that_it_can_prove() {
    let own = Some(GapEffect::Modules {
        modules: vec![ModuleName::new("pkg.lib.a")],
    });
    for name in GapName::ALL {
        let found = (name.effect(Some("pkg.lib.a")), name.effect(None));
        let expected = match name {
            GapName::Workspace | GapName::PathDependency | GapName::PackageConfig => {
                (Some(GapEffect::EveryModule), Some(GapEffect::EveryModule))
            }
            GapName::TargetMissing
            | GapName::TargetNotSelected
            | GapName::TargetOutside
            | GapName::UnsupportedUri
            | GapName::UriNotLiteral
            | GapName::Mirrors
            | GapName::Isolate => (own.clone(), None),
            _ => (None, None),
        };
        assert_eq!(found, expected, "{name:?}");
    }
}
