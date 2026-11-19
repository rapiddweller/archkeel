# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The layout of large and stacked levels of the Explorer, in a headless Chrome.

The self report holds a part with more than 600 modules ("Rust core"). Its Modules view took
three seconds of ELK work and then showed an empty corner of a 50000 px sheet (issue 1488); two
stacked boxes got an edge that ran around the upper box (issue 1489); the first view after a
drill was drawn at 40 percent, too small to read (issue 1490).
"""

import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from explorer_support import Browser, browser, serve, write_pages

PAGES = {"system": (None, "docs/architecture/architecture-system.json")}
CORE = "PART%3Acore"
# The click on a view and the ready layout: 3 s before issue 1488, 0.1 s after it on a laptop.
BUDGET_SECONDS = 2.0
# The readable floor of `fit` in flow/canvas.js (READABLE_SCALE).
READABLE_ZOOM = 85
STATE = "document.getElementById('flow').dataset.layoutState"
VISIBLE_CARDS = """(() => {
  const canvas = document.querySelector('#flow .flow-canvas').getBoundingClientRect();
  return [...document.querySelectorAll('#flow svg [data-uml-id] .card')].filter((card) => {
    const box = card.getBoundingClientRect();
    return box.left >= canvas.left && box.right <= canvas.right
      && box.top >= canvas.top && box.bottom <= canvas.bottom;
  }).length;
})()"""


@pytest.fixture(scope="module")
def site(release_core: Path, tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    folder = tmp_path_factory.mktemp("site")
    write_pages(release_core, folder, PAGES)
    with serve(folder) as base:
        yield base


@pytest.fixture(scope="module")
def page(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Browser]:
    with browser(tmp_path_factory.mktemp("profile")) as driven:
        yield driven


def choose(page: Browser, content: str) -> float:
    """Click the Components or Modules choice; the seconds until the layout is ready."""
    started = time.monotonic()
    page.evaluate(
        "document.querySelector("
        f"'#flow .atlas-content-choice button[data-content=\"{content}\"]').click()"
    )
    page.wait(f"{STATE} === 'ready' || {STATE} === 'error'", timeout=30)
    elapsed = time.monotonic() - started
    assert page.evaluate(STATE) == "ready"
    page.settle()
    return elapsed


@pytest.mark.parametrize("width", [320, 390])
def test_mobile_navigation_and_details_do_not_overlap(
    site: str, tmp_path_factory: pytest.TempPathFactory, width: int
) -> None:
    with browser(tmp_path_factory.mktemp("mobile"), width=width, height=844) as page:
        page.send(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=844,
            deviceScaleFactor=1,
            mobile=True,
        )
        page.send("Emulation.setTouchEmulationEnabled", enabled=True)
        page.open(f"{site}/system.html")
        page.evaluate("document.querySelector('#flow').scrollIntoView()")
        visible = """(selector) => {
          const e = document.querySelector(selector), r = e.getBoundingClientRect();
          const hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
          return r.width > 0 && r.height > 0 && (e === hit || e.contains(hit));
        }"""
        assert page.evaluate(f"({visible})('#flow [data-content=modules]')")

        def tap(selector: str) -> None:
            point = page.evaluate(f"""(() => {{
              const e = document.querySelector({selector!r});
              e.scrollIntoView({{block: "center", inline: "center"}});
              const r = e.getBoundingClientRect();
              return {{x: r.x + r.width / 2, y: r.y + r.height / 2}};
            }})()""")
            page.send("Input.dispatchTouchEvent", type="touchStart", touchPoints=[point])
            page.send("Input.dispatchTouchEvent", type="touchEnd", touchPoints=[])

        tap("#flow .node")
        overlap = page.evaluate("""(() => {
          const a = document.querySelector('#flow .flow-inspector').getBoundingClientRect();
          const b = document.querySelector('#flow .ak-bottom-center').getBoundingClientRect();
          return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        })()""")
        assert not overlap
        assert page.evaluate("""(() => {
          const canvas = document.querySelector('#flow .flow-canvas').getBoundingClientRect();
          return canvas.width > 100 && canvas.height > 100
            && [...document.querySelectorAll('#flow .node')].some((node) => {
              const box = node.getBoundingClientRect();
              return box.right > canvas.left && box.left < canvas.right
                && box.bottom > canvas.top && box.top < canvas.bottom;
            });
        })()""")
        page.evaluate("document.querySelector('#flow [data-browse-component]').scrollIntoView()")
        assert page.evaluate(f"({visible})('#flow [data-browse-component]')")
        page.evaluate("document.querySelector('#flow .flow-inspector details').open = true")
        assert page.evaluate("""(() => {
          const e = document.querySelector('#flow .flow-inspector');
          e.scrollTop = e.scrollHeight;
          return e.scrollTop > 0;
        })()""")
        page.evaluate("document.querySelector('#flow .flow-inspector').scrollTop = 0")
        tap("#flow [data-browse-component]")
        page.settle()
        assert page.evaluate("document.querySelector('#flow').dataset.content") == "modules"
        assert page.state()["scope"] == "PART:shell"
        page.evaluate("document.querySelector('#flow .flow-breadcrumb button').focus()")
        assert page.evaluate("document.activeElement?.dataset.atlasDepth") == "0"
        page.send(
            "Input.dispatchKeyEvent",
            type="keyDown",
            key="Enter",
            code="Enter",
            windowsVirtualKeyCode=13,
            text="\r",
            unmodifiedText="\r",
        )
        page.send(
            "Input.dispatchKeyEvent",
            type="keyUp",
            key="Enter",
            code="Enter",
            windowsVirtualKeyCode=13,
        )
        page.settle()
        assert page.state()["scope"] is None
        tap("#flow .ak-bottom-center button")
        assert (
            page.evaluate(
                "document.querySelector('#flow .ak-bottom-center button')"
                ".getAttribute('aria-pressed')"
            )
            == "true"
        )
        tap("#flow [aria-label='Zoom in']")
        zoom = page.evaluate("parseInt(document.querySelector('.flow-zoom-value').textContent)")
        assert zoom > 85


@pytest.mark.parametrize("content", ["components", "modules"])
def test_each_view_of_the_rust_core_is_ready_in_budget(
    site: str, page: Browser, content: str
) -> None:
    other = "components" if content == "modules" else "modules"
    page.open(f"{site}/system.html?scope={CORE}&content={other}")
    elapsed = choose(page, content)
    assert elapsed < BUDGET_SECONDS, f"{content}: ready after {elapsed:.2f} s"
    assert page.evaluate(VISIBLE_CARDS) > 0, "the canvas shows no complete box"


def test_component_cards_use_whole_counts_and_a_short_layer_description(
    site: str, page: Browser
) -> None:
    page.open(f"{site}/system.html?scope={CORE}&content=components")
    weights = page.evaluate(
        "Array.from(document.querySelectorAll('#flow .atlas-weight'), e => e.textContent)"
    )
    assert weights and all(" module" in text for text in weights), weights
    layer = page.evaluate(
        "document.querySelector('#flow [data-uml-id=\"LAYER:PART:core:evaluation\"] .meta')"
        ".textContent"
    )
    assert "components in this layer" in layer
    assert layer.endswith("."), layer


def test_a_level_with_too_many_modules_groups_them_by_component(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html?scope={CORE}&content=modules")
    scene = page.evaluate(
        "(() => { const s = ArchkeelFlow.state().scene;"
        " return { nodes: s.nodes.length, grouped: s.grouped,"
        " counts: s.nodes.reduce((sum, n) => sum + (n.group || 0), 0) }; })()"
    )
    modules = scene["grouped"]["modules"]
    assert modules > scene["grouped"]["limit"] == 30
    assert scene["nodes"] <= 30
    assert scene["counts"] == modules
    assert f"{modules} observed modules in" in page.evaluate(
        "document.querySelector('.atlas-summary').textContent"
    )
    page.evaluate(
        "document.querySelector('#flow [data-uml-id=\"LAYER:PART:core:evaluation\"]')"
        ".dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))"
    )
    page.settle()
    assert page.state()["scope"] == "LAYER:PART:core:evaluation"
    nodes = page.evaluate("ArchkeelFlow.state().scene.nodes.map((n) => n.kind)")
    assert nodes and set(nodes) == {"module"}


def test_a_modules_view_over_one_screen_shows_only_modules_that_share_no_prefix(
    site: str, page: Browser
) -> None:
    # AD-794: above the limit a level is grouped by its structure, never by ranges of names; what
    # stays over the limit are modules that share no directory and no file prefix.
    page.open(f"{site}/system.html")
    assert page.evaluate("ArchkeelFlow.reportScene.atlas.module_box_limit") == 30
    over = page.evaluate(
        "(() => { const R = ArchkeelFlow.reportScene, A = R.atlas;"
        " const prefix = (n) => n.module.path.split('/').at(-1).split('.')[0].split('_')[0];"
        " return A.levels.map((l) => [l.parent_id, R.atlasModuleScene(l, 'diagram').nodes])"
        ".filter(([, nodes]) => nodes.length > A.module_box_limit)"
        ".map(([id, nodes]) => {"
        " const loose = nodes.filter((n) => n.kind === 'module').map(prefix);"
        " return [id, loose.length, new Set(loose).size]; }); })()"
    )
    assert all(loose == distinct for _, loose, distinct in over), over
    assert not page.evaluate(
        "ArchkeelFlow.reportScene.atlas.components.filter((c) => / to /.test(c.label)).length"
    )


def test_a_large_leaf_component_groups_its_modules_by_directory(site: str, page: Browser) -> None:
    # Issue 1603: a component with 64 modules and no parts drew all 64 module boxes.
    leaf = "COMP-NATIVE-PY-SURVEY"
    page.open(f"{site}/system.html?scope={leaf}&content=modules")
    scene = page.evaluate(
        "(() => { const s = ArchkeelFlow.state().scene;"
        " return { grouped: s.grouped, boxes: s.nodes.map((n) => [n.id, n.group || 0]) }; })()"
    )
    assert scene["grouped"]["modules"] > scene["grouped"]["limit"]
    assert all(box.startswith(f"FILES:{leaf}:") for box, _ in scene["boxes"])
    assert sum(count for _, count in scene["boxes"]) == scene["grouped"]["modules"]
    declared = next(box for box, _ in scene["boxes"] if box.endswith(":declared/"))
    page.evaluate(
        f"document.querySelector('#flow [data-uml-id=\"{declared}\"]')"
        ".dispatchEvent(new MouseEvent('click', { bubbles: true }))"
    )
    page.evaluate("document.querySelector('#flow .flow-inspector details').open = true")
    sheet = page.evaluate("document.querySelector('#flow .flow-inspector').innerText")
    assert "DIRECTORY FACT SHEET" in sheet.upper()
    assert "py-survey owns the modules in the contract" in sheet
    assert "Decided by architect" not in sheet
    page.evaluate(
        f"document.querySelector('#flow [data-uml-id=\"{declared}\"]')"
        ".dispatchEvent(new MouseEvent('dblclick', { bubbles: true }))"
    )
    page.settle()
    assert page.state()["scope"] == declared
    paths = page.evaluate("ArchkeelFlow.state().scene.nodes.map((n) => n.module.path)")
    assert paths and all("/survey/declared/" in path for path in paths)
    # The module keeps its owner in the contract: the box only places it on the map.
    owners = page.evaluate("ArchkeelFlow.state().scene.nodes.map((n) => n.module.component_id)")
    assert set(owners) == {leaf}


def test_a_module_path_breaks_at_a_slash(site: str, page: Browser) -> None:
    page.open(
        f"{site}/system.html?scope=FILES%3ACOMP-NATIVE-PY-SURVEY%3Adeclared%2F&content=modules"
    )
    lines = page.evaluate(
        "[...document.querySelectorAll('#flow svg [data-uml-kind=\"module\"] .meta')]"
        ".map((meta) => [...meta.children].map((line) => line.textContent))"
    )
    assert lines
    for card in lines:
        assert all(line.endswith("/") for line in card[:-1]), card


def test_a_module_box_carries_the_language_of_its_part(site: str, page: Browser) -> None:
    # The Language perspective said "No tagged objects on this diagram" on a module level.
    page.open(f"{site}/system.html?scope=SHELL-ENTRY&content=modules")
    found = page.evaluate(
        "(() => { const flow = document.getElementById('flow');"
        " const boxes = [...flow.querySelectorAll('svg [data-uml-kind=\"module\"]')];"
        " return { boxes: boxes.length,"
        " tagged: boxes.map((g) => g.querySelector('.ak-tag')?.dataset.language || null),"
        " chips: [...flow.querySelectorAll('.ak-chip')].map((c) => c.textContent.trim()),"
        " empty: flow.textContent.includes('No tagged objects on this diagram') }; })()"
    )
    assert found["boxes"] > 0
    assert found["tagged"] == ["python"] * found["boxes"], found
    assert found["chips"] == [f"python{found['boxes']}"] or found["chips"] == [
        f"python {found['boxes']}"
    ], found
    assert not found["empty"]


def test_two_stacked_boxes_get_a_direct_edge(site: str, page: Browser) -> None:
    # A tall canvas makes the layout wrap the two parts of the system into two rows.
    page.open(f"{site}/system.html")
    shell, core, points = page.evaluate(
        """(async () => {
          document.querySelector('#flow .flow-canvas').style.height = '3000px';
          const card = { 'PART:shell': 178, 'PART:core': 178 };
          const result = await ArchkeelReportLayout.layoutAtlas({
            componentOverview: true, parentId: null,
            nodes: [{ id: 'PART:shell' }, { id: 'PART:core' }],
            edges: [{ id: 'e', layoutId: 'interface:x', source: 'PART:shell',
              target: 'PART:core', label: 'Core frame protocol' }],
            components: [], cardWidth: 200, cardHeights: card });
          document.querySelector('#flow .flow-canvas').style.height = '';
          const box = (id) => { const p = result.positions[`component:${id}`];
            return [p.x, p.x + 200, p.y, p.y + card[id]]; };
          return [box('PART:shell'), box('PART:core'),
            result.routes.get('edge:interface:x').points];
        })()"""
    )
    assert shell[3] <= core[2] and shell[0] < core[1] and core[0] < shell[1], "not stacked"
    assert len(points) - 2 <= 2, points


def test_the_first_view_after_opening_a_level_link_is_readable(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate("ArchkeelFlow.openComponent('PART:core')")
    page.settle()
    page.evaluate("new Promise((done) => requestAnimationFrame(() => requestAnimationFrame(done)))")
    zoom = page.evaluate("document.querySelector('#flow .flow-zoom-value').textContent")
    assert int(zoom.rstrip("%")) >= READABLE_ZOOM
    assert page.evaluate(VISIBLE_CARDS) > 0


FIRST_VIEW = """(() => {
  const flow = document.getElementById('flow');
  const canvas = flow.querySelector('.flow-canvas').getBoundingClientRect();
  const inside = (r) => r.left >= canvas.left && r.right <= canvas.right
    && r.top >= canvas.top && r.bottom <= canvas.bottom;
  const cards = [...flow.querySelectorAll('svg [data-uml-id] .card')];
  const labels = [...flow.querySelectorAll('svg .atlas-edge-label')];
  const first = cards.map((c) => c.getBoundingClientRect())
    .sort((a, b) => a.left + a.top - b.left - b.top)[0];
  const hint = flow.querySelector('.rp-scroll-hint');
  return { zoom: parseInt(flow.querySelector('.flow-zoom-value').textContent, 10),
    cards: cards.length, cardsIn: cards.filter((c) => inside(c.getBoundingClientRect())).length,
    labels: labels.length, labelsIn: labels.filter((l) => inside(l.getBoundingClientRect())).length,
    firstIn: Boolean(first && inside(first)), overflow: flow.dataset.overflow,
    hint: hint && !hint.hidden ? hint.textContent : null };
})()"""


def test_a_double_click_fits_the_opened_level(site: str, page: Browser) -> None:
    page.open(f"{site}/system.html")
    page.evaluate("""(() => {
      const shell = document.querySelector('#flow svg [data-uml-id="PART:shell"]');
      shell.dispatchEvent(new MouseEvent('click', {bubbles: true}));
      shell.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
    })()""")
    page.settle()
    assert page.state()["scope"] == "PART:shell"
    view = page.evaluate(FIRST_VIEW)
    assert view["cards"] and view["labels"], view
    assert (view["cardsIn"], view["labelsIn"]) == (view["cards"], view["labels"]), view
    assert view["overflow"] == "", view


@pytest.mark.parametrize(("width", "height"), [(1500, 1100), (1920, 1300)])
def test_the_first_view_shows_the_whole_graph_or_starts_at_its_top_left_box(
    tmp_path: Path, site: str, width: int, height: int
) -> None:
    # Issue 1618: the first view cut the graph at the right edge with no sign that it goes on.
    with browser(tmp_path, width=width, height=height) as sized:
        views = {}
        for name, query in [
            ("system", ""),
            ("collector", "scope=LAYER%3APART%3Acore%3Acollector"),
            ("core", f"scope={CORE}"),
        ]:
            sized.open(f"{site}/system.html?{query}")
            sized.evaluate(
                "new Promise((d) => requestAnimationFrame(() => requestAnimationFrame(d)))"
            )
            views[name] = sized.evaluate(FIRST_VIEW)
    for name in ("system", "collector"):
        view = views[name]
        assert view["zoom"] >= READABLE_ZOOM, view
        assert (view["cardsIn"], view["labelsIn"]) == (view["cards"], view["labels"]), view
        assert (view["overflow"], view["hint"]) == ("", None), view
    core = views["core"]
    assert core["zoom"] == READABLE_ZOOM, core
    assert core["firstIn"], core
    assert "right" in core["overflow"].split(), core
    assert core["hint"] == "Scroll or press Shift 1 to fit", core


def test_a_language_badge_is_never_cut(site: str, page: Browser) -> None:
    # The badge of the Python shell read "pyth…": its width was a guess of the text length.
    for query in ("", f"scope={CORE}", "scope=PART%3Ashell"):
        page.open(f"{site}/system.html?{query}")
        badges = page.evaluate(
            "[...document.querySelectorAll('#flow svg [data-uml-id]')].filter((g) =>"
            " g.querySelector('.ak-tag')).map((g) => { const tag = g.querySelector('.ak-tag');"
            " const text = tag.querySelector('text'), rect = tag.querySelector('rect');"
            " const kind = g.querySelector('.stereotype');"
            " const visible = kind && kind.getAttribute('visibility') !== 'hidden';"
            " return { text: text.textContent, room: rect.getBBox().width - 12,"
            " length: text.getComputedTextLength(), left: tag.getBBox().x + tag.transform.baseVal"
            ".consolidate().matrix.e, kindRight: visible ? 16 + kind.getComputedTextLength() : 0,"
            " title: g.dataset.akTag }; })"
        )
        assert badges, query
        for badge in badges:
            assert badge["text"] == badge["title"], badge
            assert badge["length"] <= badge["room"] + 0.5, badge
            assert badge["kindRight"] < badge["left"], badge


LONG_TITLE = "Python extension module pydantic_core._pydantic_core (PyO3 binding, maturin)"
LABEL_OVERLAPS = """(() => {
  const flow = document.getElementById('flow');
  const boxes = [...flow.querySelectorAll('svg [data-uml-id] .card')]
    .map((c) => c.getBoundingClientRect());
  const canvas = flow.querySelector('.flow-canvas').getBoundingClientRect();
  return [...flow.querySelectorAll('svg .atlas-edge-label')].map((label) => {
    const r = label.getBoundingClientRect();
    return { text: label.textContent,
      overlaps: boxes.filter((b) => r.left < b.right && r.right > b.left && r.top < b.bottom
        && r.bottom > b.top).length,
      inside: r.left >= canvas.left && r.right <= canvas.right }; });
})()"""


@pytest.mark.parametrize(("width", "height"), [(1440, 900), (1440, 1300)])
def test_an_edge_label_stays_outside_every_box(
    tmp_path: Path, site: str, width: int, height: int
) -> None:
    # Issue 1659: a long interface title started under its source box and was cut off.
    import urllib.request  # noqa: PLC0415

    page = urllib.request.urlopen(f"{site}/system.html").read().decode()  # noqa: S310
    assert page.count('"Core frame protocol"') >= 1
    folder = tmp_path / "site"
    folder.mkdir()
    (folder / "long.html").write_text(page.replace('"Core frame protocol"', f'"{LONG_TITLE}"'))
    with serve(folder) as base, browser(tmp_path / "profile", width=width, height=height) as tall:
        tall.open(f"{base}/long.html")
        labels = tall.evaluate(LABEL_OVERLAPS)
    assert [label["text"] for label in labels] == [LONG_TITLE]
    assert all(label["overlaps"] == 0 for label in labels), labels


def test_every_chip_line_stays_inside_its_box(site: str, page: Browser) -> None:
    # Issue 1694: "12 open gaps · 1 unused permission inside" ran past the right edge of its box.
    for query in ("", f"scope={CORE}", "scope=PART%3Ashell"):
        page.open(f"{site}/system.html?{query}")
        chips = page.evaluate(
            "[...document.querySelectorAll('#flow svg [data-uml-id]')].flatMap((g) => {"
            " const card = g.querySelector('.card')?.getBoundingClientRect();"
            " return [...g.querySelectorAll('.atlas-finding-chip, .atlas-deviation-chip')]"
            ".map((c) => { const r = c.getBoundingClientRect();"
            " return { text: c.textContent, inside: r.left >= card.left && r.right <= card.right"
            " && r.bottom <= card.bottom, box: g.dataset.umlId }; }); })"
        )
        assert all(chip["inside"] for chip in chips), [c for c in chips if not c["inside"]]
        assert not any(" · " in chip["text"] for chip in chips), chips


def test_a_layer_of_one_component_draws_no_frame_around_that_component(
    site: str, page: Browser
) -> None:
    # The shell part has layers of one component (`commands`, `frame`) and layers of
    # several. The box of a layer that holds one component is that component: the Modules view drew
    # two nested frames with the same label and the same stereotype for it. A layer of several
    # components is a real parent and keeps its frame.
    page.open(f"{site}/system.html?scope=PART%3Ashell&content=modules")
    frames = {
        frame["id"]: frame
        for frame in page.evaluate(
            "[...document.querySelectorAll('#flow svg .uml-frame')].map((g) => {"
            " const r = g.querySelector('.target-frame').getBoundingClientRect();"
            " return { id: g.dataset.umlId, label: g.dataset.label,"
            " box: [r.left, r.top, r.right, r.bottom] }; })"
        )
    }

    def inside(inner: str, outer: str) -> bool:
        (a, b, c, d), (e, f, g, h) = frames[inner]["box"], frames[outer]["box"]
        return e <= a and f <= b and c <= g and d <= h

    for single in ("commands", "frame"):
        assert f"LAYER:PART:shell:{single}" not in frames
        assert f"SHELL-{single.upper()}" in frames
    assert inside("SHELL-ENTRY", "LAYER:PART:shell:entry")
    assert inside("SHELL-EXPLORER-MCP", "LAYER:PART:shell:entry")
    assert inside("SHELL-JSON", "LAYER:PART:shell:foundation")
    assert inside("SHELL-GAPS", "LAYER:PART:shell:present")
    nested = [
        (inner, outer)
        for inner in frames
        for outer in frames
        if inner != outer
        and frames[inner]["label"] == frames[outer]["label"]
        and inside(inner, outer)
    ]
    assert not nested, nested
