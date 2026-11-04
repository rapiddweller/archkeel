/** AD-290: Level 3: the functions of one module, their calls, and the modules that call in or are called as stubs. */
import { useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { View, viewHref } from "../components";
import { layoutModule, parseKey } from "../level-layout";
import { Level, Model, counted, links, shortName, tailName } from "../model";
import { FocusList, LevelCanvas, Workbench, focusRows, useFocus } from "../workbench";

const fileOf = (model: Model, module: number): string => model.graph.modules[module][1].split("/").pop() ?? "";

export function ModuleLevel(props: { model: Model; module: number; chat: ChatState }) {
  const { model, module } = props;
  const [all, setAll] = useState(false);
  const focus = useFocus();
  const layout = useMemo(() => layoutModule(model, module, all), [model, module, all]);
  const [, , component] = model.graph.modules[module];
  const packages = model.folders[module];
  const functions = model.members[module];
  const unknown = functions.reduce((sum, symbol) => sum + model.graph.symbols[symbol][5], 0);
  const part = focus.key === null ? null : parseKey(focus.key);
  const focusName = part === null ? "" : part.stub === null ? shortName(model, part.id) : fileOf(model, part.id);
  return (
    <Workbench
      model={model}
      where={{ level: Level.Module, id: module, pkg: null }}
      chat={props.chat}
      symbol={null}
      focus={focus}
      name="Module"
      here={{
        name: model.graph.modules[module][0],
        counts: `${counted(functions.length, "function")} · ${unknown} unknown calls`,
        meaning:
          "A card is a function. Hover a card to see its callers and callees, in this module and in the modules at the sides; click to pin, Esc clears, double click or Enter opens its lens. Stubs on the left are modules that call in; stubs on the right are modules that are called.",
        up: viewHref(View.Component, component, packages.length > 0 ? packages.join(".") : undefined),
        upName: packages.length > 0 ? packages[packages.length - 1] : model.graph.components[component][0],
      }}
      summary={`${counted(functions.length, "function")} · ${counted(layout.stubs.length, "stub")} · ${unknown} unknown`}
      canvas={{
        width: layout.width,
        height: layout.height,
        label: "Functions",
        fitKey: `${module}:${all}`,
        children: (
          <LevelCanvas
            layout={layout}
            level={Level.Function}
            focus={focus}
            colour={() => component}
            plate="module"
            headIn="Called from"
            headOut="Calls into"
            onOpen={() => setAll(true)}
            fnName={(symbol) => shortName(model, symbol)}
            card={(symbol) => ({
              href: viewHref(View.Explore, symbol),
              name: model.graph.symbols[symbol][1],
              title: `${model.graph.modules[module][0]}.${model.graph.symbols[symbol][1]}`,
              meta: `${counted(links(model, symbol), "link")}${model.graph.symbols[symbol][5] > 0 ? ` · ${model.graph.symbols[symbol][5]} unknown` : ""}`,
            })}
            stub={(stub) => ({
              href: viewHref(View.Module, stub.id),
              name: fileOf(model, stub.id),
              title: model.graph.modules[stub.id][0],
              path: tailName(model.graph.modules[stub.id][0], 26),
            })}
          />
        ),
      }}
      details={
        <FocusList
          focus={focus}
          title={focusName}
          open={part !== null && part.stub === null ? { href: viewHref(View.Explore, part.id), label: `Open ${focusName} in the lens →` } : null}
          rows={focusRows(model, layout, focus.key, (far) => {
            const other = parseKey(far);
            return other.stub === null
              ? { name: shortName(model, other.id), href: viewHref(View.Explore, other.id), where: `${fileOf(model, module)}:${model.graph.symbols[other.id][2]}` }
              : { name: fileOf(model, other.id), href: viewHref(View.Module, other.id), where: model.graph.modules[other.id][0] };
          })}
        />
      }
    />
  );
}
