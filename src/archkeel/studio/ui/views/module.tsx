/** AD-290: Level 3: the functions of one module, their calls, and the modules that call in or are called as stubs. */
import { useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { View, viewHref } from "../components";
import { Side } from "../lens-layout";
import { KeyKind, LevelText, layoutModule, parseKey } from "../level-layout";
import { Level, Model, counted, neighbors, shortName } from "../model";
import { FocusList, LevelCanvas, Selection, Workbench, focusRows, functionRows, useFocus } from "../workbench";

const fileOf = (model: Model, module: number): string => model.graph.modules[module][1].split("/").pop() ?? "";

export function ModuleLevel(props: { model: Model; module: number; chat: ChatState }) {
  const { model, module } = props;
  const [all, setAll] = useState(false);
  const focus = useFocus();
  const meta = (symbol: number): string => `${counted(neighbors(model, symbol), "link")}${model.graph.symbols[symbol][5] > 0 ? ` · ? ${model.graph.symbols[symbol][5]}` : ""}`;
  const text: LevelText = {
    card: (symbol) => ({ name: model.graph.symbols[symbol][1], facts: [meta(symbol)] }),
    stub: (ref) => ({ name: fileOf(model, Number(ref)), facts: ["✓ 9999 · ✎ 9999"] }),
  };
  const layout = useMemo(() => layoutModule(model, module, all, text), [model, module, all]);
  const [, , component] = model.graph.modules[module];
  const packages = model.folders[module];
  const functions = model.members[module];
  const unknown = functions.reduce((sum, symbol) => sum + model.graph.symbols[symbol][5], 0);
  const part = focus.pinned === null ? null : parseKey(focus.pinned);
  const selection = () => {
    if (part === null || part.kind === KeyKind.Tile) return null;
    if (part.kind === KeyKind.Card) {
      const symbol = Number(part.ref);
      const [, name, line, kind, definition, unresolved, outside] = model.graph.symbols[symbol];
      return (
        <Selection
          name={name}
          kind={kind === "method" ? "Method" : kind === "class" ? "Class" : "Function"}
          where={["Architecture", model.graph.components[component][0], ...packages, fileOf(model, module), name].join(" › ")}
          facts={[
            `${counted(model.incoming[symbol].length, "caller")} · ${counted(model.outgoing[symbol].length, "callee")}`,
            `${unresolved} calls with no known target`,
            ...(outside > 0 ? [`${outside} calls outside the scan`] : []),
            `defined at ${fileOf(model, module)}:${line}`,
          ]}
          text={definition}
          open={{ href: viewHref(View.Explore, symbol), label: "Open in the lens →" }}
        />
      );
    }
    const other = Number(part.ref);
    const stub = layout.stubs.find((item) => item.ref === part.ref);
    return (
      <Selection
        name={model.graph.modules[other][0]}
        kind="Module"
        where={["Architecture", model.graph.components[model.graph.modules[other][2]][0], ...model.folders[other], fileOf(model, other)].join(" › ")}
        facts={stub === undefined ? [] : [`${stub.proven} proven function links · ${stub.claim} claim`, part.stub === Side.In ? "calls into this module" : "is called from this module"]}
        open={{ href: viewHref(View.Module, other), label: "Open the module →" }}
      />
    );
  };
  return (
    <Workbench
      model={model}
      where={{ level: Level.Module, id: module, pkg: null }}
      chat={props.chat}
      symbol={null}
      focus={{ active: focus.active, clear: focus.clear }}
      name="Module"
      here={{
        name: model.graph.modules[module][0],
        counts: `${counted(functions.length, "function")} · ${unknown} unknown calls`,
        meaning:
          "A card is a function. Click selects, double click or Enter opens its lens. Hover a card to see its callers and callees. Stubs on the left are modules that call in; stubs on the right are modules that are called.",
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
            card={(symbol) => ({ href: viewHref(View.Explore, symbol), name: model.graph.symbols[symbol][1], meta: meta(symbol) })}
            stub={(stub) => ({ href: viewHref(View.Module, Number(stub.ref)), name: fileOf(model, Number(stub.ref)) })}
          />
        ),
      }}
      details={
        <FocusList
          focus={focus}
          selection={selection()}
          rows={
            part !== null && part.kind === KeyKind.Card
              ? functionRows(model, Number(part.ref), module)
              : focusRows(model, layout, focus.pinned, (far) => {
                  const other = parseKey(far);
                  return { name: other.kind === KeyKind.Stub ? fileOf(model, Number(other.ref)) : other.ref, href: viewHref(View.Module, Number(other.ref)), where: model.graph.modules[Number(other.ref)]?.[0] ?? "" };
                })
          }
        />
      }
    />
  );
}
