# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A private guard can reach a foreign reader through a sink, a destructor or a macro."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from rust_repository import APP, CRATE_RULES, repository, statuses, validate
from test_collector_false_pass_rust_trait_dispatch import NO_A_TO_B, STORED_VALUE, _app

pytestmark = pytest.mark.skipif(shutil.which("rustc") is None, reason="rustc is the oracle")


@pytest.mark.parametrize("transfer", ["sink-binding", "clone-in-drop", "macro-constructor"])
def test_a_private_local_guard_can_reach_an_erased_reader(
    tmp_path: Path, release_core: Path, transfer: str
) -> None:
    body = """
        use std::sync::atomic::{AtomicBool, Ordering};
        static HIT: AtomicBool = AtomicBool::new(false);
        fn publish<T: Send + 'static>(value: T) { crate::slot::put(Box::new(value)); }
        pub fn drive() -> bool {
    """
    if transfer == "sink-binding":
        body += """
            struct G;
            impl Drop for G { fn drop(&mut self) { HIT.store(true, Ordering::SeqCst); } }
            #[cfg(feature="handoff")] let drop: fn(_) = publish;
            let guard = G;
            drop(guard);
        """
    elif transfer == "clone-in-drop":
        body += """
            #[derive(Clone)] struct G(bool);
            impl Drop for G {
                fn drop(&mut self) {
                    HIT.store(true, Ordering::SeqCst);
                    #[cfg(feature="handoff")]
                    if std::mem::take(&mut self.0) { publish(self.clone()); }
                }
            }
            let guard = G(true);
            std::mem::drop(guard);
        """
    else:
        body += """
            struct G(bool);
            impl Drop for G {
                fn drop(&mut self) { if self.0 { HIT.store(true, Ordering::SeqCst); } }
            }
            let guard = G(matches!(true, true));
            std::mem::drop(guard);
        """
    body += """
            HIT.store(false, Ordering::SeqCst);
            crate::a::run();
            HIT.load(Ordering::SeqCst)
        }
    """
    files = _app(
        {
            "lib.rs": "mod a; mod b; mod slot;\n"
            '#[test] fn witness() { assert_eq!(b::drive(), cfg!(feature="handoff")); }',
            "a.rs": "pub fn run() { drop(crate::slot::take()); }",
            "b.rs": body,
            "slot.rs": STORED_VALUE,
        }
    )
    files["crates/app/Cargo.toml"] = APP + "[features]\nhandoff = []\n"
    if transfer == "macro-constructor":
        lib = "crates/app/src/lib.rs"
        files[lib] = '#[cfg(feature="handoff")] #[macro_use] mod macros;\n' + files[lib]
        files["crates/app/src/macros.rs"] = """
            macro_rules! matches {
                ($v:expr, $p:pat) => {{
                    $crate::slot::put(Box::new(G(true)));
                    ::std::matches!($v, $p)
                }};
            }
        """
    root = repository(tmp_path / "repo", release_core, files, rules=(*CRATE_RULES, NO_A_TO_B))
    src = root / "crates/app/src/lib.rs"
    for handoff in (False, True):
        exe = tmp_path / ("witness.exe" if os.name == "nt" else "witness")
        cfg = ["--cfg", 'feature="handoff"'] if handoff else []
        subprocess.run(["rustc", "--edition=2021", "--test", *cfg, src, "-o", exe], check=True)
        subprocess.run([exe, "--exact", "witness"], check=True)
    result = validate(root)
    status = statuses(result)["NO-A-TO-B"]
    assert status in {"FAIL", "UNKNOWN"}
    if status == "UNKNOWN":
        pairs = result["frame"]["explain"]["holds"]["rules"]["NO-A-TO-B"]["pairs"]
        assert {"source": "native.app.a", "target": "native.app.b"} in pairs
