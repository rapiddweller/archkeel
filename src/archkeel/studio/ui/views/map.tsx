/** AD-290: Map: the components of the snapshot as a dependency graph of the measured calls. */
import { useMemo, useState } from "preact/hooks";
import { Box, Page, ProofLegend, ProofMark, View, viewHref } from "../components";
import { Evidence, PROOF, Proof, proofOf } from "../evidence";
import { MAP_CARD, MapLine, layoutMap } from "../map-layout";
import { Model, compact, counted, fileName, links, shortName, tailPath } from "../model";
import { Viewport } from "../viewport";

const PAIRS_SHOWN = 16;

const calls = (count: number): string => `${compact(count)} ${count === 1 ? "call" : "calls"}`;

interface Pair {
  readonly from: number;
  readonly to: number;
}

const proofWord = (partial: boolean): string => PROOF.find((kind) => kind.proof === proofOf(partial))?.word ?? "";

function Pairs(props: { model: Model; pair: Pair }) {
  const { model, pair } = props;
  const flow = model.flows.find((item) => item.from === pair.from && item.to === pair.to);
  const names = model.graph.components;
  const found = new Map<string, { source: number; target: number; partial: boolean; line: number }>();
  for (const index of flow?.edges ?? []) {
    const [source, target, partial, line] = model.graph.edges[index];
    const key = `${source}:${target}`;
    const known = found.get(key);
    if (known === undefined || (known.partial && !partial)) found.set(key, { source, target, partial, line });
  }
  const shown = [...found.values()]
    .sort((a, b) => links(model, b.target) - links(model, a.target))
    .slice(0, PAIRS_SHOWN);
  const partial = flow?.partial ?? 0;
  const calls = flow?.calls ?? 0;
  return (
    <>
      <Box title={`Dependency · ${names[pair.from][0]} to ${names[pair.to][0]}`}>
        <p>
          {calls} calls · {found.size} distinct pairs
        </p>
        <p>
          <ProofMark proof={Proof.Proven} /> {calls - partial} · <ProofMark proof={Proof.Claim} /> {partial}
        </p>
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
        {found.size > PAIRS_SHOWN ? <p class="more">+{found.size - PAIRS_SHOWN} more pairs</p> : null}
      </Box>
    </>
  );
}

function Line(props: { line: MapLine; hot: number | null; selected: boolean; onHot: (component: number | null) => void; onPick: () => void }) {
  const { line, hot } = props;
  const touches = hot !== null && (line.from === hot || line.to === hot);
  const kind = line.mostlyPartial ? Proof.Claim : Proof.Proven;
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

function MapView(props: { model: Model }) {
  const { model } = props;
  const layout = useMemo(() => layoutMap(model), [model]);
  const [hot, setHot] = useState<number | null>(null);
  const [pair, setPair] = useState<Pair | null>(null);
  const [details, setDetails] = useState(() => matchMedia("(min-width: 1500px)").matches);
  const total = model.flows.reduce((sum, flow) => sum + flow.calls, 0);
  const neighbors = (component: number): boolean =>
    hot !== null && (component === hot || model.flows.some((f) => (f.from === hot && f.to === component) || (f.to === hot && f.from === component)));
  return (
    <div class="workbench" data-details={details}>
      <header class="toolbar">
        <h1>Map</h1>
        <span class="summary">
          {model.graph.components.length} components · {model.flows.length} dependencies · {compact(total)} calls between components
        </span>
        <ProofLegend />
        <button type="button" class="toggle" aria-pressed={details} onClick={() => setDetails(!details)}>
          Details
        </button>
      </header>
      <section class="canvas">
        <Viewport width={layout.width} height={layout.height} label="Component map" fitKey={model}>
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
                onPick={() => {
                  setPair({ from: line.from, to: line.to });
                  setDetails(true);
                }}
              />
            ))}
          </svg>
          {layout.lines
            .filter((line) => line.labeled)
            .map((line) => {
              const proof = line.mostlyPartial ? Proof.Claim : Proof.Proven;
              const kind = PROOF.find((item) => item.proof === proof);
              const [from, to] = [model.graph.components[line.from][0], model.graph.components[line.to][0]];
              return (
                <button
                  key={`${line.from}:${line.to}`}
                  type="button"
                  class={`count ${proof}`}
                  aria-label={`${counted(line.calls, "call")} from ${from} to ${to}, ${proofWord(line.mostlyPartial)}`}
                  style={{ left: `${line.middle[0]}px`, top: `${line.middle[1]}px` }}
                  onClick={() => {
                    setPair({ from: line.from, to: line.to });
                    setDetails(true);
                  }}
                  onMouseEnter={() => setHot(line.from)}
                  onMouseLeave={() => setHot(null)}
                >
                  {compact(line.calls)} <span aria-hidden="true">{kind?.glyph}</span> {kind?.word}
                </button>
              );
            })}
          {model.graph.components.map(([id, responsibility], component) => {
            const [x, y] = layout.positions[component];
            const stat = model.stats[component];
            const box = { left: `${x}px`, top: `${y}px`, width: `${MAP_CARD.width}px`, height: `${MAP_CARD.height}px` };
            const body = (
              <>
                <h2>
                  <span class="dot" aria-hidden="true" />
                  {id}
                  <small>{layout.bandNames[layout.band[component]]}</small>
                </h2>
                <p>{responsibility || "No responsibility declared."}</p>
                <span class="chips">
                  <span class="chip">{counted(stat.modules, "module")}</span>
                  <span class="chip">{counted(stat.symbols, "function")}</span>
                  <span class="chip">{calls(stat.callsIn)} in</span>
                  <span class="chip">{calls(stat.callsOut)} out</span>
                  {stat.withUnknown > 0 ? (
                    <span class="chip unknown">
                      <span aria-hidden="true">?</span> {counted(stat.withUnknown, "function")} with unknown calls
                    </span>
                  ) : null}
                </span>
                {stat.busiest !== null ? (
                  <span class="busiest">
                    busiest: <b>{shortName(model, stat.busiest)}</b> · {counted(links(model, stat.busiest), "link")}
                  </span>
                ) : null}
              </>
            );
            const className = `map-card comp-${component % 10}${neighbors(component) ? " hl" : ""}`;
            return stat.busiest === null ? (
              <div key={id} class={className} style={box}>
                {body}
              </div>
            ) : (
              <a
                key={id}
                class={className}
                style={box}
                href={viewHref(View.Explore, stat.busiest)}
                onMouseEnter={() => setHot(component)}
                onMouseLeave={() => setHot(null)}
                onFocus={() => setHot(component)}
                onBlur={() => setHot(null)}
              >
                {body}
              </a>
            );
          })}
        </Viewport>
      </section>
      <aside class="details" aria-label="Details">
        {pair === null ? (
          <Box title="Dependencies">
            <p>Hover a card to light its lines. Select a line or a count to see the calls behind it.</p>
            <p>Open a card to see its busiest function in the lens.</p>
          </Box>
        ) : (
          <Pairs model={model} pair={pair} />
        )}
      </aside>
    </div>
  );
}

export function ArchMap(props: { model: Model | null }) {
  if (props.model === null) {
    return (
      <Page title="Map" lead="No map yet. Overview shows the progress.">
        {null}
      </Page>
    );
  }
  return <MapView model={props.model} />;
}
