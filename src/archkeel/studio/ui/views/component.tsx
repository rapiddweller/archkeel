/** AD-290: Level 2: the modules of one component, on plates by package, with the other components as stubs. */
import { useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { View, viewHref } from "../components";
import { layoutComponent, parseKey } from "../level-layout";
import { Level, Model, counted, shortName } from "../model";
import { FocusList, LevelCanvas, Workbench, focusRows, useFocus } from "../workbench";

/** The package one step up: `a.b` to `a`, a first package to the component. */
const parentOf = (component: number, pkg: string | null): string =>
  pkg === null || !pkg.includes(".") ? viewHref(View.Component, component) : viewHref(View.Component, component, pkg.slice(0, pkg.lastIndexOf(".")));

const fileOf = (model: Model, module: number): string => model.graph.modules[module][1].split("/").pop() ?? "";

export function ComponentLevel(props: { model: Model; component: number; pkg: string | null; chat: ChatState }) {
  const { model, component, pkg } = props;
  const [opened, setOpened] = useState<ReadonlySet<string>>(new Set());
  const focus = useFocus();
  const layout = useMemo(() => layoutComponent(model, component, pkg, opened), [model, component, pkg, opened]);
  const [id] = model.graph.components[component];
  const modules = layout.cards.length + layout.tiles.reduce((sum, tile) => sum + tile.hidden, 0);
  const functions = model.graph.modules.reduce((sum, row, module) => sum + (row[2] === component ? model.members[module].length : 0), 0);
  const cardInfo = (module: number) => {
    const unknown = model.members[module].reduce((sum, symbol) => sum + model.graph.symbols[symbol][5], 0);
    return {
      href: viewHref(View.Module, module),
      name: fileOf(model, module),
      title: `${model.graph.modules[module][0]} (${model.graph.modules[module][1]})`,
      meta: `${counted(model.members[module].length, "function")}${unknown > 0 ? ` · ${unknown} unknown` : ""}`,
    };
  };
  const stubInfo = (other: number) => ({
    href: viewHref(View.Component, other),
    name: model.graph.components[other][0],
    title: `${model.graph.components[other][0]}: ${model.graph.components[other][1]}`,
    path: model.graph.components[other][1] || "component",
  });
  const part = focus.key === null ? null : parseKey(focus.key);
  const focusName = part === null ? "" : part.stub === null ? fileOf(model, part.id) : model.graph.components[part.id][0];
  return (
    <Workbench
      model={model}
      where={{ level: Level.Component, id: component, pkg }}
      chat={props.chat}
      symbol={null}
      focus={focus}
      name="Component"
      here={{
        name: pkg === null ? id : `${id} › ${pkg.split(".").join(" › ")}`,
        counts: `${counted(modules, "module")} · ${counted(functions, "function")}`,
        meaning:
          "A card is a module. Hover a card to see who calls it and whom it calls; click to pin, Esc clears, double click or Enter opens it. Stubs on the left call into this component; stubs on the right are called by it.",
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
            fnName={(symbol) => shortName(model, symbol)}
            card={cardInfo}
            stub={(stub) => stubInfo(stub.id)}
          />
        ),
      }}
      details={
        <FocusList
          focus={focus}
          title={focusName}
          open={part !== null && part.stub === null ? { href: viewHref(View.Module, part.id), label: `Open ${focusName} →` } : null}
          rows={focusRows(model, layout, focus.key, (far) => {
            const other = parseKey(far);
            return other.stub === null
              ? { name: fileOf(model, other.id), href: viewHref(View.Module, other.id), where: model.graph.modules[other.id][0] }
              : { name: model.graph.components[other.id][0], href: viewHref(View.Component, other.id), where: "component" };
          })}
        />
      }
    />
  );
}
