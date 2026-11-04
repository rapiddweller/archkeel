/** AD-290: Level 3: the functions of one module, their calls, and the modules that call in or are called as stubs. */
import { useMemo } from "preact/hooks";
import type { ChatState } from "../chat";
import { Box, View, viewHref } from "../components";
import { Side } from "../lens-layout";
import { LevelStub, layoutModule } from "../level-layout";
import { Level, Model, counted, links } from "../model";
import { Counts, LevelCanvas, Workbench } from "../workbench";

const fileOf = (model: Model, module: number): string => model.graph.modules[module][1].split("/").pop() ?? "";

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
              <a href={viewHref(View.Module, stub.id)} title={model.graph.modules[stub.id][0]}>
                {fileOf(model, stub.id)}
              </a>{" "}
              <span class="where">{model.graph.modules[stub.id][0]}</span>
              <br />
              <Counts tally={stub} /> <span class="where">function links</span>
            </li>
          ))}
        </ul>
      )}
    </Box>
  );
}

export function ModuleLevel(props: { model: Model; module: number; chat: ChatState }) {
  const { model, module } = props;
  const layout = useMemo(() => layoutModule(model, module), [model, module]);
  const [, , component] = model.graph.modules[module];
  const packages = model.folders[module];
  const functions = model.members[module];
  const unknown = functions.reduce((sum, symbol) => sum + model.graph.symbols[symbol][5], 0);
  return (
    <Workbench
      model={model}
      where={{ level: Level.Module, id: module, pkg: null }}
      chat={props.chat}
      symbol={null}
      name="Module"
      here={{
        name: model.graph.modules[module][0],
        counts: `${counted(functions.length, "function")} · ${unknown} unknown calls`,
        meaning:
          "A card is a function. A line is a call between two functions of this module. Stubs on the left are modules that call in; stubs on the right are modules that are called. Click a function for its lens, a stub to open that module.",
        up: viewHref(View.Component, component, packages.length > 0 ? packages.join(".") : undefined),
        upName: packages.length > 0 ? packages[packages.length - 1] : model.graph.components[component][0],
      }}
      summary={`${counted(functions.length, "function")} · ${counted(layout.stubs.length, "stub")} · ${unknown} unknown`}
      canvas={{
        width: layout.width,
        height: layout.height,
        label: "Functions",
        fitKey: module,
        children: (
          <LevelCanvas
            layout={layout}
            level={Level.Function}
            colour={() => component}
            headIn="Called from"
            headOut="Calls into"
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
