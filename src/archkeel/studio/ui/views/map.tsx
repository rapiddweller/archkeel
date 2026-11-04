/** AD-290: Map: the components of the snapshot as a dependency graph of the measured calls. */
import { useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { Badge, Box, Page, ProofLegend, ProofMark, View, viewHref } from "../components";
import { Evidence, Proof, proofKind, proofOf } from "../evidence";
import { MAP_CARD, MapLine, layoutMap } from "../map-layout";
import { Level, Model, Tally, counted, fileName, links, pairs, shortName, tailPath } from "../model";
import { ComponentSource, ContractState } from "../vocabulary";
import { Counts, Workbench } from "../workbench";

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
  const neighbors = (component: number): boolean =>
    hot !== null && (component === hot || model.flows.some((f) => (f.from === hot && f.to === component) || (f.to === hot && f.from === component)));
  return (
    <Workbench
      model={model}
      where={{ level: Level.Map, id: null, pkg: null }}
      chat={props.chat}
      symbol={null}
      reveal={pair}
      name="Map"
      here={{
        name: "Architecture",
        counts: `${counted(model.graph.components.length, "component")} · ${counted(model.graph.modules.length, "module")} · ${counted(model.graph.symbols.length, "function")}`,
        meaning:
          "A card is a component. A line is the sum of the call sites between two components. Click a card to open its modules.",
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
          {model.graph.components.map(([id, responsibility], component) => {
            const [x, y] = layout.positions[component];
            const stat = model.stats[component];
            const box = { left: `${x}px`, top: `${y}px`, width: `${MAP_CARD.width}px`, height: `${MAP_CARD.height}px` };
            return (
              <a
                key={id}
                class={`map-card comp-${component % 10}${neighbors(component) ? " hl" : ""}`}
                data-drill
                style={box}
                href={viewHref(View.Component, component)}
                title={`${id}: ${responsibility || "No responsibility declared."}`}
                onMouseEnter={() => setHot(component)}
                onMouseLeave={() => setHot(null)}
                onFocus={() => setHot(component)}
                onBlur={() => setHot(null)}
              >
                <h2>
                  <span class="dot" aria-hidden="true" />
                  <span class="nm">{id}</span>
                  <small>{layout.bandNames[layout.band[component]]}</small>
                </h2>
                <p class="desc">{responsibility || "No responsibility declared."}</p>
                <span class="stat first">
                  {counted(stat.modules, "module")} · {counted(stat.symbols, "function")}
                </span>
                <span class="stat">
                  in <Counts tally={stat.callsIn} />
                </span>
                <span class="stat">
                  out <Counts tally={stat.callsOut} />
                </span>
                {stat.withUnknown > 0 ? (
                  <span class="stat unknown">
                    <span aria-hidden="true">?</span> {counted(stat.withUnknown, "function")} with unknown calls
                  </span>
                ) : null}
                {stat.busiest !== null ? (
                  <span class="stat busiest">
                    busiest: <b>{shortName(model, stat.busiest)}</b> · {counted(links(model, stat.busiest), "link")}
                  </span>
                ) : null}
              </a>
            );
          })}
        </>
      ) }}
      details={
        <>
          {pair === null ? (
            <Box title="Dependencies">
              <p>Hover a card to light its lines. Select a line or a count to see the calls behind it.</p>
              <p>Click a card to open the modules of that component.</p>
            </Box>
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
