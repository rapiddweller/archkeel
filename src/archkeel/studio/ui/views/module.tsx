/** AD-290: Level 3: the functions of one module, their calls, and the modules that call in or are called as stubs. */
import { useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { View, viewHref } from "../components";
import { KeyKind, layoutModule, parseKey } from "../level-layout";
import { Level, Model, counted, neighbors, shortName, tailName } from "../model";
import { FocusList, LevelCanvas, Workbench, focusRows, functionRows, useFocus } from "../workbench";

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
  const focusName = part === null ? "" : part.kind === KeyKind.Card ? shortName(model, Number(part.ref)) : part.kind === KeyKind.Stub ? fileOf(model, Number(part.ref)) : part.ref;
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
              path: model.graph.modules[module][0],
              title: `${model.graph.modules[module][0]}.${model.graph.symbols[symbol][1]}`,
              meta: `${counted(neighbors(model, symbol), "link")}${model.graph.symbols[symbol][5] > 0 ? ` · ${model.graph.symbols[symbol][5]} unknown` : ""}`,
            })}
            stub={(stub) => ({
              href: viewHref(View.Module, Number(stub.ref)),
              name: fileOf(model, Number(stub.ref)),
              title: `${model.graph.modules[Number(stub.ref)][0]}: ${stub.proven + stub.claim} function links`,
              path: tailName(model.graph.modules[Number(stub.ref)][0], 26),
            })}
          />
        ),
      }}
      details={
        <FocusList
          focus={focus}
          title={focusName}
          open={part !== null && part.kind === KeyKind.Card ? { href: viewHref(View.Explore, Number(part.ref)), label: `Open ${focusName} in the lens →` } : null}
          rows={
            part !== null && part.kind === KeyKind.Card
              ? functionRows(model, Number(part.ref), module)
              : focusRows(model, layout, focus.key, (far) => {
                  const other = parseKey(far);
                  return { name: other.kind === KeyKind.Stub ? fileOf(model, Number(other.ref)) : `${other.ref}`, href: viewHref(View.Module, Number(other.ref)), where: model.graph.modules[Number(other.ref)]?.[0] ?? "" };
                })
          }
        />
      }
    />
  );
}
