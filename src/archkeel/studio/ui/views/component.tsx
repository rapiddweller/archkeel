/** AD-290: Level 2: the modules of one component, on plates by package, with the other components as stubs. */
import { useMemo } from "preact/hooks";
import type { ChatState } from "../chat";
import { Box, View, viewHref } from "../components";
import { LevelStub, layoutComponent } from "../level-layout";
import { Side } from "../lens-layout";
import { Level, Model, counted } from "../model";
import { Counts, LevelCanvas, Workbench } from "../workbench";

/** The package one step up: `a.b` to `a`, a first package to the component. */
const parentOf = (component: number, pkg: string | null): string =>
  pkg === null || !pkg.includes(".") ? viewHref(View.Component, component) : viewHref(View.Component, component, pkg.slice(0, pkg.lastIndexOf(".")));

function StubList(props: { model: Model; title: string; stubs: readonly LevelStub[] }) {
  const { model } = props;
  return (
    <Box title={`${props.title} · ${props.stubs.length}`}>
      {props.stubs.length === 0 ? (
        <p class="more">none</p>
      ) : (
        <ul class="pairs">
          {props.stubs.map((stub) => (
            <li key={stub.id}>
              <a href={viewHref(View.Component, stub.id)}>{model.graph.components[stub.id][0]}</a>{" "}
              <span class="where">
                <Counts tally={stub} />
              </span>
            </li>
          ))}
        </ul>
      )}
    </Box>
  );
}

export function ComponentLevel(props: { model: Model; component: number; pkg: string | null; chat: ChatState }) {
  const { model, component, pkg } = props;
  const layout = useMemo(() => layoutComponent(model, component, pkg), [model, component, pkg]);
  const [id] = model.graph.components[component];
  const modules = layout.cards.length;
  const functions = layout.cards.reduce((sum, card) => sum + model.members[card.index].length, 0);
  const inside = layout.lines.filter((line) => !line.a.startsWith("in:") && !line.b.startsWith("out:"));
  return (
    <Workbench
      model={model}
      where={{ level: Level.Component, id: component, pkg }}
      chat={props.chat}
      symbol={null}
      name="Component"
      here={{
        name: pkg === null ? id : `${id} › ${pkg.split(".").join(" › ")}`,
        counts: `${counted(modules, "module")} · ${counted(functions, "function")}`,
        meaning:
          "A card is a module. A line is the sum of the call sites between two modules. Stubs on the left call into this component; stubs on the right are called by it. Click a card to open its functions, a stub to open that component.",
        up: pkg === null ? viewHref(View.Map) : parentOf(component, pkg),
        upName: pkg === null ? "Architecture" : pkg.includes(".") ? pkg.slice(0, pkg.lastIndexOf(".")) : id,
      }}
      summary={`${counted(modules, "module")} · ${inside.length} dependenc${inside.length === 1 ? "y" : "ies"} between modules · ${counted(layout.stubs.length, "stub")}`}
      canvas={{
        width: layout.width,
        height: layout.height,
        label: "Modules",
        fitKey: `${component}:${pkg}`,
        children: (
          <LevelCanvas
            layout={layout}
            level={Level.Module}
            colour={() => component}
            headIn="Called from"
            headOut="Calls into"
            card={(module) => {
              const unknown = model.members[module].reduce((sum, symbol) => sum + model.graph.symbols[symbol][5], 0);
              return {
                href: viewHref(View.Module, module),
                name: model.graph.modules[module][1].split("/").pop() ?? "",
                title: `${model.graph.modules[module][0]} (${model.graph.modules[module][1]})`,
                meta: `${counted(model.members[module].length, "function")}${unknown > 0 ? ` · ${unknown} unknown` : ""}`,
              };
            }}
            stub={(stub) => ({
              href: viewHref(View.Component, stub.id),
              name: model.graph.components[stub.id][0],
              title: `${model.graph.components[stub.id][0]}: ${model.graph.components[stub.id][1]}`,
            })}
          />
        ),
      }}
      details={
        <>
          <StubList model={model} title="Called from" stubs={layout.stubs.filter((stub) => stub.side === Side.In)} />
          <StubList model={model} title="Calls into" stubs={layout.stubs.filter((stub) => stub.side === Side.Out)} />
        </>
      }
    />
  );
}
