/** AD-290: Level 2: the modules of one component, on plates by package, with the other components as stubs. */
import { useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { View, viewHref } from "../components";
import { Side } from "../lens-layout";
import { KeyKind, LevelText, layoutComponent, parseKey, splitRef } from "../level-layout";
import { Level, Model, counted, fileOf } from "../model";
import { FocusList, LevelCanvas, Selection, Workbench, focusRows, useFocus } from "../workbench";

/** The package one step up: `a.b` to `a`, a first package to the component. */
const parentOf = (component: number, pkg: string | null): string =>
  pkg === null || !pkg.includes(".") ? viewHref(View.Component, component) : viewHref(View.Component, component, pkg.slice(0, pkg.lastIndexOf(".")));

export function ComponentLevel(props: { model: Model; component: number; pkg: string | null; chat: ChatState }) {
  const { model, component, pkg } = props;
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());
  const focus = useFocus();
  const unknownOf = (module: number): number => model.members[module].reduce((sum, symbol) => sum + model.graph.symbols[symbol][5], 0);
  const meta = (module: number): string => `${counted(model.members[module].length, "symbol")}${unknownOf(module) > 0 ? ` · ? ${unknownOf(module)}` : ""}`;
  /** A stub of this page: another component, or another package of this component. */
  const stubName = (ref: string): string => {
    const { id: other, pkg: inner } = splitRef(ref);
    const label = model.graph.components[other][0];
    if (other === component && inner === null) return `${label} (root)`;
    return inner === null ? label : `${label} › ${inner}`;
  };
  const text: LevelText = {
    card: (module) => ({ name: fileOf(model, module), facts: [meta(module)] }),
    stub: (ref) => ({ name: stubName(ref), facts: ["9999 ✓ proven · 9999 ✎ partial"] }),
  };
  const layout = useMemo(() => layoutComponent(model, component, pkg, opened, text), [model, component, pkg, opened]);
  const [id] = model.graph.components[component];
  const modules = layout.cards.length + layout.tiles.reduce((sum, tile) => sum + tile.hidden, 0);
  const symbols = model.graph.modules.reduce((sum, row, module) => sum + (row[2] === component ? model.members[module].length : 0), 0);
  const stubHref = (ref: string): string => {
    const { id: other, pkg: inner } = splitRef(ref);
    return viewHref(View.Component, other, inner ?? undefined);
  };
  const part = focus.pinned === null ? null : parseKey(focus.pinned);
  const named = (key: string): { name: string; href: string; where: string } => {
    const far = parseKey(key);
    if (far.kind === KeyKind.Tile) return { name: far.ref, href: "#", where: "folded package" };
    if (far.kind === KeyKind.Card) {
      return { name: fileOf(model, Number(far.ref)), href: viewHref(View.Module, Number(far.ref)), where: model.graph.modules[Number(far.ref)][0] };
    }
    return { name: stubName(far.ref), href: stubHref(far.ref), where: model.graph.components[splitRef(far.ref).id][0] };
  };
  const selection = () => {
    if (part === null) return null;
    if (part.kind === KeyKind.Card) {
      const module = Number(part.ref);
      const [name, file] = model.graph.modules[module];
      const trail = ["Architecture", id, ...model.folders[module], fileOf(model, module)].join(" › ");
      return (
        <Selection
          name={name}
          kind="Module"
          where={trail}
          facts={[`${counted(model.members[module].length, "symbol")}`, `${unknownOf(module)} calls with no known target`, `file ${file}`]}
          open={{ href: viewHref(View.Module, module), label: "Open the module →" }}
        />
      );
    }
    if (part.kind === KeyKind.Stub) {
      const { id: other, pkg: inner } = splitRef(part.ref);
      const stub = layout.stubs.find((item) => item.ref === part.ref);
      return (
        <Selection
          name={stubName(part.ref)}
          kind={inner === null ? "Component" : "Package"}
          where={["Architecture", model.graph.components[other][0], ...(inner === null ? [] : [inner])].join(" › ")}
          facts={stub === undefined ? [] : [`${stub.proven} proven call sites · ${stub.partial} partial`, part.stub === Side.In ? "calls into this page" : "is called from this page"]}
          text={model.graph.components[other][1] || undefined}
          open={{ href: stubHref(part.ref), label: `Open ${inner === null ? "the component" : "the package"} →` }}
        />
      );
    }
    return null;
  };
  return (
    <Workbench
      model={model}
      where={{ level: Level.Component, id: component, pkg }}
      chat={props.chat}
      symbol={null}
      focus={{ active: focus.active, clear: focus.clear }}
      name="Component"
      here={{
        name: pkg === null ? id : `${id} › ${pkg.split(".").join(" › ")}`,
        counts: `${counted(modules, "module")} · ${counted(symbols, "symbol")}`,
        meaning:
          "A card is a module. Click selects, double click or Enter opens. Hover a card to see who calls it and whom it calls. Stubs on the left call into this page; stubs on the right are called by it.",
        up: pkg === null ? viewHref(View.Map) : parentOf(component, pkg),
        upName: pkg === null ? "Architecture" : pkg.includes(".") ? pkg.slice(0, pkg.lastIndexOf(".")) : id,
      }}
      summary={`${counted(modules, "module")} · ${counted(layout.stubs.length, "stub")}`}
      canvas={{
        width: layout.width,
        height: layout.height,
        label: "Modules",
        fitKey: `${component}:${pkg}:${opened.size}`,
        children: (
          <LevelCanvas
            layout={layout}
            level={Level.Module}
            focus={focus}
            colour={() => component}
            plate="package"
            headIn="Called from"
            headOut="Calls into"
            onOpen={(label) => setOpened(new Set([...opened, label]))}
            fnName={(symbol) => model.graph.symbols[symbol][1].split(".").pop() ?? ""}
            card={(module) => ({ href: viewHref(View.Module, module), name: fileOf(model, module), meta: meta(module) })}
            stub={(stub) => ({ href: stubHref(stub.ref), name: stubName(stub.ref) })}
          />
        ),
      }}
      details={<FocusList focus={focus} selection={selection()} rows={focusRows(model, layout, focus.pinned, named)} />}
    />
  );
}
