/** AD-290: Map: the components of the snapshot as a dependency graph of the measured calls. */
import { useEffect, useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { Badge, Box, Page, ProofLegend, ProofMark, View, viewHref } from "../components";
import { Evidence, Proof, proofKind, proofOf } from "../evidence";
import { MAP_CARD, MapLine, layoutMap } from "../map-layout";
import { Level, Model, Tally, counted, fileName, links, pairs, shortName, tailPath } from "../model";
import { ComponentSource, ContractState } from "../vocabulary";
import { ARROWS, Counts, Glyphs, Selection, Workbench, nearest } from "../workbench";

const PAIRS_SHOWN = 16;

const spoken = ({ proven, claim }: Tally): string =>
  [proven > 0 || claim === 0 ? `${proven} proven` : "", claim > 0 ? `${claim} claim` : ""].filter(Boolean).join(", ");

interface Pair {
  readonly from: number;
  readonly to: number;
}

function Pairs(props: { model: Model; pair: Pair }) {
  const { model, pair } = props;
  const flow = model.flows.find((item) => item.from === pair.from && item.to === pair.to);
  const names = model.graph.components;
  const found = flow === undefined ? [] : pairs(model, flow);
  const shown = [...found].sort((a, b) => links(model, b.target) - links(model, a.target)).slice(0, PAIRS_SHOWN);
  return (
    <>
      <Box title={`Dependency · ${names[pair.from][0]} to ${names[pair.to][0]}`}>
        <p>
          <Counts tally={flow ?? { proven: 0, claim: 0 }} /> · {counted(found.length, "distinct pair")}
        </p>
        <p class="more">A partly resolved call with two candidates is one claim.</p>
      </Box>
      <Box title="Calls behind this line, most shared callees first" evidence={Evidence.Observed}>
        <ul class="pairs">
          {shown.map((item) => (
            <li key={`${item.source}:${item.target}`}>
              <ProofMark proof={proofOf(item.partial)} />{" "}
              <a href={viewHref(View.Explore, item.source)}>{shortName(model, item.source)}</a> calls{" "}
              <a href={viewHref(View.Explore, item.target)}>{shortName(model, item.target)}</a>{" "}
              <span class="where">
                {tailPath(fileName(model, item.source))}:{item.line}
              </span>
            </li>
          ))}
        </ul>
        {found.length > PAIRS_SHOWN ? <p class="more">+{found.length - PAIRS_SHOWN} more pairs</p> : null}
      </Box>
    </>
  );
}

function Line(props: { line: MapLine; hot: number | null; selected: boolean; onHot: (component: number | null) => void; onPick: () => void }) {
  const { line, hot } = props;
  const touches = hot !== null && (line.from === hot || line.to === hot);
  // A line is proven only when it holds no claim.
  const kind = proofOf(line.claim > 0);
  const state = hot === null ? (line.strong ? "strong" : "faint") : touches ? "lit" : "dim";
  return (
    <g>
      <path class={`link ${kind} ${state}${props.selected ? " selected" : ""}`} d={line.path} stroke-width={line.width} />
      <path
        class="hit"
        d={line.path}
        onClick={props.onPick}
        onMouseEnter={() => props.onHot(line.from)}
        onMouseLeave={() => props.onHot(null)}
      />
    </g>
  );
}

function MapView(props: { model: Model; contract: ContractState; chat: ChatState }) {
  const { model } = props;
  const layout = useMemo(() => layoutMap(model), [model]);
  const [hot, setHot] = useState<number | null>(null);
  const [pair, setPair] = useState<Pair | null>(null);
  // A click selects a component; a double click or Enter opens it.
  const [selected, setSelected] = useState<number | null>(null);
  const neighbors = (component: number): boolean =>
    hot !== null && (component === hot || model.flows.some((f) => (f.from === hot && f.to === component) || (f.to === hot && f.from === component)));
  const boxes = useMemo(
    () => new Map(layout.positions.map(([x, y], component) => [`${component}`, { x, y, width: MAP_CARD.width, height: layout.cardHeight }])),
    [layout],
  );
  useEffect(() => {
    const listener = (event: KeyboardEvent): void => {
      const step = ARROWS[event.key];
      if (step === undefined || event.target instanceof HTMLInputElement) return;
      const from = selected === null ? "" : `${selected}`;
      const next = nearest(boxes, from === "" ? "0" : from, step, selected === null);
      if (next === null) return;
      event.preventDefault();
      setSelected(Number(next));
      document.querySelector<HTMLElement>(`[data-key="${next}"]`)?.focus({ preventScroll: true });
    };
    addEventListener("keydown", listener);
    return () => removeEventListener("keydown", listener);
  }, [boxes, selected]);
  const stat = selected === null ? null : model.stats[selected];
  const flowsOf = (component: number, out: boolean) => model.flows.filter((flow) => (out ? flow.from === component : flow.to === component)).sort((a, b) => b.proven + b.claim - (a.proven + a.claim));
  return (
    <Workbench
      model={model}
      where={{ level: Level.Map, id: null, pkg: null }}
      chat={props.chat}
      symbol={null}
      reveal={pair}
      focus={{ active: selected !== null, clear: () => setSelected(null) }}
      name="Map"
      here={{
        name: "Architecture",
        counts: `${counted(model.graph.components.length, "component")} · ${counted(model.graph.modules.length, "module")} · ${counted(model.graph.symbols.length, "function")}`,
        meaning: "A card is a component. A line is the sum of the call sites between two components. Click selects, double click or Enter opens its modules.",
        up: null,
        upName: null,
      }}
      toolbar={<Source source={model.graph.components_from} contract={props.contract} />}
      summary={
        <>
          {model.graph.components.length} components · {model.flows.length} dependencies · <Counts tally={model.crossing} /> calls between
          components
        </>
      }
      canvas={{ width: layout.width, height: layout.height, label: "Component map", fitKey: model, children: (
        <>
          {layout.bandNames.map((name, band) => (
            <p
              key={name}
              class="band"
              style={{ left: `${MAP_CARD.left + band * (MAP_CARD.width + MAP_CARD.gapX)}px`, top: "28px" }}
            >
              {name}
            </p>
          ))}
          <svg class="lines" width={layout.width} height={layout.height} aria-hidden="true">
            {layout.lines.map((line) => (
              <Line
                key={`${line.from}:${line.to}`}
                line={line}
                hot={hot}
                selected={pair?.from === line.from && pair?.to === line.to}
                onHot={setHot}
                onPick={() => setPair({ from: line.from, to: line.to })}
              />
            ))}
          </svg>
          {layout.lines
            .filter((line) => line.labeled)
            .map((line) => {
              const [x, y] = line.middle;
              const [from, to] = [model.graph.components[line.from][0], model.graph.components[line.to][0]];
              return (
                <button
                  key={`n:${line.from}:${line.to}`}
                  type="button"
                  class={`count ${proofOf(line.claim > 0)}`}
                  style={{ left: `${x}px`, top: `${y}px` }}
                  aria-label={`${counted(line.calls, "call")} from ${from} to ${to}: ${spoken(line)}`}
                  onClick={() => setPair({ from: line.from, to: line.to })}
                  onMouseEnter={() => setHot(line.from)}
                  onMouseLeave={() => setHot(null)}
                >
                  <Counts tally={line} />
                </button>
              );
            })}
          {model.graph.components.map(([id], component) => {
            const [x, y] = layout.positions[component];
            const own = model.stats[component];
            const box = { left: `${x}px`, top: `${y}px`, width: `${MAP_CARD.width}px`, height: `${layout.cardHeight}px` };
            const href = viewHref(View.Component, component);
            return (
              <a
                key={id}
                data-key={`${component}`}
                class={`map-card comp-${component % 10}${neighbors(component) ? " hl" : ""}${selected === component ? " pinned" : ""}`}
                data-drill
                style={box}
                href={href}
                aria-pressed={selected === component}
                onClick={(event) => {
                  if (event.detail === 0 || event.metaKey || event.ctrlKey) return;
                  event.preventDefault();
                  if (event.detail === 1) setSelected(selected === component ? null : component);
                  else location.hash = href;
                }}
                onMouseEnter={() => setHot(component)}
                onMouseLeave={() => setHot(null)}
                onFocus={() => setHot(component)}
                onBlur={() => setHot(null)}
              >
                <h2>
                  <span class="dot" aria-hidden="true" />
                  <span class="nm">{id}</span>
                </h2>
                <span class="stat">
                  {counted(own.modules, "module")} · {counted(own.symbols, "function")}
                </span>
                <span class="stat">
                  in <Glyphs tally={own.callsIn} /> · out <Glyphs tally={own.callsOut} />
                </span>
              </a>
            );
          })}
        </>
      ) }}
      details={
        <>
          {selected === null || stat === null ? null : (
            <>
              <Selection
                name={model.graph.components[selected][0]}
                kind="Component"
                where={`Architecture › ${model.graph.components[selected][0]}`}
                facts={[
                  `${counted(stat.modules, "module")} · ${counted(stat.symbols, "function")}`,
                  `calls in: ${stat.callsIn.proven} proven · ${stat.callsIn.claim} claim`,
                  `calls out: ${stat.callsOut.proven} proven · ${stat.callsOut.claim} claim`,
                  `${counted(stat.withUnknown, "function")} with unknown calls`,
                  ...(stat.busiest === null ? [] : [`busiest function: ${shortName(model, stat.busiest)}`]),
                ]}
                text={model.graph.components[selected][1] || "No responsibility declared."}
                open={{ href: viewHref(View.Component, selected), label: "Open the component →" }}
              />
              {(["Called by", "Calls"] as const).map((title, index) => (
                <Box key={title} title={title}>
                  <ul class="pairs">
                    {flowsOf(selected, index === 1).slice(0, 8).map((flow) => {
                      const other = index === 1 ? flow.to : flow.from;
                      return (
                        <li key={other}>
                          <a href={viewHref(View.Component, other)}>{model.graph.components[other][0]}</a> <Glyphs tally={flow} />
                        </li>
                      );
                    })}
                    {flowsOf(selected, index === 1).length === 0 ? <li class="more">none</li> : null}
                  </ul>
                </Box>
              ))}
            </>
          )}
          {pair === null ? (
            selected === null ? (
              <Box title="Dependencies">
                <p>Click a card to select it. Hover a card to light its lines. Select a line or a count to see the calls behind it.</p>
              </Box>
            ) : null
          ) : (
            <Pairs model={model} pair={pair} />
          )}
          <Box title="Calls">
            <ProofLegend />
          </Box>
        </>
      }
    />
  );
}

/** Where the components come from: the contract is an architect decision, the layout is observed. */
function Source(props: { source: ComponentSource; contract: ContractState }) {
  if (props.source === ComponentSource.CONTRACT) {
    return <Badge evidence={Evidence.Target}>components: declared by the contract</Badge>;
  }
  const reason = props.contract === ContractState.INVALID ? " (the contract does not load)" : "";
  return <Badge evidence={Evidence.Observed}>{`components: observed package layout${reason}`}</Badge>;
}

export function ArchMap(props: { model: Model | null; contract: ContractState; chat: ChatState }) {
  if (props.model === null) {
    return (
      <Page title="Map" lead="No map yet. Overview shows the progress.">
        {null}
      </Page>
    );
  }
  return <MapView model={props.model} contract={props.contract} chat={props.chat} />;
}
