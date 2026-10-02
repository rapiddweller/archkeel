# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Export a skills-only plugin from the same source the CLI installs."""

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New plugin directory; must not exist.")
    target = parser.parse_args().output.resolve()
    if Path(str(target) + ".zip").exists():
        parser.error(f"ZIP already exists: {target}.zip")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir()
    skill = target / "skills/archkeel"
    skill.mkdir(parents=True)
    shutil.copyfile(ROOT / "skills/archkeel/SKILL.md", skill / "SKILL.md")
    shutil.copyfile(ROOT / "LICENSE", target / "LICENSE")
    shutil.copyfile(ROOT / "plugin.json", target / "plugin.json")
    claude = target / ".claude-plugin"
    claude.mkdir()
    shutil.copyfile(ROOT / ".claude-plugin/plugin.json", claude / "plugin.json")
    assets = target / "assets"
    assets.mkdir()
    shutil.copyfile(
        ROOT / "src/archkeel/render/assets/archkeel-mark.svg", assets / "archkeel-mark.svg"
    )
    # A ZIP dereferences repository links and contains only the distributable plugin files.
    shutil.make_archive(str(target), "zip", target)
    print(target)


if __name__ == "__main__":
    main()
