import json

import pytest
from test_exact_module_ownership import _component, _rule

from archkeel.check.report import run_saved_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import canonical_report_bytes, observation_payload
from archkeel.ir.decisions import rule_assessments


def _guard_rule(identifier):
    return _rule(
        "forbidden_effect_under_condition",
        id=identifier,
        source="sample.core",
        target="sample.core._effect",
        condition={
            "kind": "parameter",
            "owner": "sample.core.generate",
            "name": "seeded",
        },
    )


@pytest.mark.parametrize("columnar", [False, True])
@pytest.mark.parametrize(("guard", "expected"), [("if seeded", "FAIL"), ("if not seeded", "PASS")])
def test_guarded_effect_root_and_mount_replay_bind_the_same_path_inventory(
    tmp_path, columnar, guard, expected
):
    inner = {
        "schema_version": "3.13.0",
        "components": [_component("core", ["sample.core"])],
        "rules": [_guard_rule("MOUNTED")],
    }
    outer = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"]) | {"inside": "inner.json"}],
        "rules": [_guard_rule("ROOT")],
    }
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Decision.\n",
        "contract.json": json.dumps(outer),
        "inner.json": json.dumps(inner),
        "sample/__init__.py": "",
        "sample/core.py": f"""def _effect():
    return None

def generate(seeded: bool):
    {guard}:
        _effect()
""",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.coverage
    assessments = {
        row.id: row for row in rule_assessments(result.observation, undecided_by_rule={})
    }
    for identifier in ("ROOT", "all:MOUNTED"):
        assert assessments[identifier].status == expected
        assert assessments[identifier].evaluation_proven

    raw = observation_payload(result.observation)
    path = tmp_path / "saved.json"
    path.write_bytes(canonical_report_bytes(raw) if columnar else json.dumps(raw).encode("utf-8"))
    replayed = {row.id: row for row in run_saved_report(path).rule_assessments}
    assert replayed == assessments

    receipts = {
        row["rule_ids"][0]: row
        for row in raw["scope_observations"]
        if row["kind"] == "rule_evaluation" and row["rule_ids"] in (["ROOT"], ["all:MOUNTED"])
    }
    assert set(receipts) == {"ROOT", "all:MOUNTED"}
    for receipt in receipts.values():
        receipt["data"]["call_scope_proof"]["binding_id"] = "0" * 64
    path.write_bytes(canonical_report_bytes(raw) if columnar else json.dumps(raw).encode("utf-8"))
    tampered = {row.id: row for row in run_saved_report(path).rule_assessments}
    for identifier in ("ROOT", "all:MOUNTED"):
        assert tampered[identifier].status == ("FAIL" if expected == "FAIL" else "UNKNOWN")
        assert not tampered[identifier].evaluation_proven


@pytest.mark.parametrize("columnar", [False, True])
def test_saved_report_keeps_member_guard_unknown_after_opaque_call(tmp_path, columnar):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                id="MEMBER_MUTATION",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "member", "owner": "sample.core.Generator", "name": "seeded"},
            )
        ],
    }
    files = {
        "pyproject.toml": '[project]\nrequires-python = ">=3.11"\n',
        "docs/architecture/sample.md": "Decision.\n",
        "contract.json": json.dumps(contract),
        "sample/__init__.py": "",
        "sample/core.py": """def _effect():
    return None

class Generator:
    def __init__(self):
        self.seeded: bool = False

    def reset(self):
        self.seeded = True

    def generate(self):
        if not self.seeded:
            self.reset()
            _effect()
""",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.coverage
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven

    raw = observation_payload(result.observation)
    path = tmp_path / "saved.json"
    path.write_bytes(canonical_report_bytes(raw) if columnar else json.dumps(raw).encode("utf-8"))
    [replayed] = run_saved_report(path).rule_assessments
    assert replayed.id == assessment.id
    assert replayed.status == "UNKNOWN"
    assert not replayed.evaluation_proven
