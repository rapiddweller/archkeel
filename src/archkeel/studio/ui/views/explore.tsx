/** AD-290: Explore: the lens around one function, with its structure, place and search. */
import { useMemo, useState } from "preact/hooks";
import type { ChatState } from "../chat";
import { Box, Page, ProofMark, View, viewHref } from "../components";
import { Evidence, Proof, proofOf } from "../evidence";
import { LensItem, LensLayout, OpenGroup, Rect, Side, layoutLens } from "../lens-layout";
import {
  Level,
  Link,
  Model,
  counted,
  componentOf,
  fileName,
  fullName,
  locate,
  moduleIndex,
  shortName,
  tailName,
  tailPath,
} from "../model";
import { Workbench } from "../workbench";

const TAIL = 34;
const LIST_SHOWN = 30;

const place = (box: Rect): Record<string, string> => ({
  left: `${box.x}px`,
  top: `${box.y}px`,
  width: `${box.width}px`,
  height: `${box.height}px`,
});

/** The true count of unknown calls; the sample holds the first few. */
const unknownText = (model: Model, symbol: number): string => {
  const total = model.graph.symbols[symbol][5];
  const shown = model.unknown[symbol].length;
  return shown < total ? `${total} unknown (first ${shown} shown)` : `${total} unknown`;
};

const colour = (component: number): string => `comp-${component % 10}`;

function Item(props: { model: Model; placed: Rect & { item: LensItem; side: Side }; onOpen: (open: OpenGroup | null) => void; onHot: (hot: boolean) => void }) {
  const { model, placed } = props;
  const { item } = placed;
  switch (item.kind) {
    case "node": {
      const proof = proofOf(item.partial);
      return (
        <a
          class={`lens-card ${proof}`}
          style={place(placed)}
          href={viewHref(View.Explore, item.symbol)}
          title={fullName(model, item.symbol)}
          onMouseEnter={() => props.onHot(true)}
          onMouseLeave={() => props.onHot(false)}
          onFocus={() => props.onHot(true)}
          onBlur={() => props.onHot(false)}
        >
          <b>{model.graph.symbols[item.symbol][1]}</b>
          <span class="meta">
            <ProofMark proof={proof} /> · {tailPath(fileName(model, item.symbol))}:{model.graph.symbols[item.symbol][2]}
          </span>
        </a>
      );
    }
    case "group":
      return (
        <button type="button" class="lens-card group" style={place(placed)} onClick={() => props.onOpen({ side: placed.side, group: item.group })}>
          <b>{item.group}</b>
          <span class="meta">
            {counted(item.count, placed.side === Side.In ? "caller" : "callee")} · open
          </span>
        </button>
      );
    case "back":
      return (
        <button type="button" class="lens-card more" style={place(placed)} onClick={() => props.onOpen(null)}>
          All groups
        </button>
      );
    case "text":
      return (
        <p class="lens-card more" style={place(placed)}>
          {item.text}
        </p>
      );
  }
}

function Lens(props: { model: Model; layout: LensLayout; center: number; onOpen: (open: OpenGroup | null) => void }) {
  const { model, layout, center } = props;
  const names = model.graph.modules;
  const [, , , , , unknown, outside] = model.graph.symbols[center];
  // The line of the card under the pointer shows its direction: a dot from the caller to the callee.
  const [hot, setHot] = useState<number | null>(null);
  const calm = matchMedia("(prefers-reduced-motion: reduce)").matches;
  return (
    <>
      {[...layout.plates, layout.centerPlate].map((plate, index) => (
        <div key={`${plate.module}:${index}`} class={`plate ${colour(names[plate.module][2])}`} style={place(plate)}>
          <span title={names[plate.module][0]}>
            <i class="dot" aria-hidden="true" />
            {tailName(names[plate.module][3], TAIL)}
          </span>
        </div>
      ))}
      <svg class="lines" width={layout.width} height={layout.height} aria-hidden="true">
        {layout.lines.map((line, index) => (
          <path key={index} class={`route ${line.kind}${hot !== null && line.item === hot ? " hot" : ""}`} d={line.path} />
        ))}
        {layout.lines
          .filter((line) => hot !== null && line.item === hot)
          .map((line) => (
            <g key={`dot:${line.item}`} class={`focus-line ${line.kind === "claim" ? "claim" : "proven"}`}>
              <circle class="port" cx={line.from[0]} cy={line.from[1]} r="2.5" />
              <circle class="port" cx={line.to[0]} cy={line.to[1]} r="2.5" />
              {calm ? null : <circle class="flow" r="3" style={{ offsetPath: `path("${line.path}")` }} />}
            </g>
          ))}
      </svg>
      {layout.heads.map((head) => (
        <p key={head.text} class="head" style={{ left: `${head.x}px`, top: `${head.y}px` }}>
          {head.text}
        </p>
      ))}
      {layout.items.map((placed, index) => (
        <Item key={index} model={model} placed={placed} onOpen={props.onOpen} onHot={(on) => setHot(on ? index : null)} />
      ))}
      <div class="lens-card center" style={place(layout.center)} title={fullName(model, center)}>
        <b>{model.graph.symbols[center][1]}</b>
        <span class="def">{model.graph.symbols[center][4]}</span>
        <span class="chips">
          <span class="chip">{model.graph.components[componentOf(model, center)][0]}</span>
          <span class="chip">
            {tailPath(fileName(model, center))}:{model.graph.symbols[center][2]}
          </span>
          <span class="chip">
            {counted(model.incoming[center].length, "caller")} · {counted(model.outgoing[center].length, "callee")}
          </span>
          {unknown > 0 ? <span class="chip unknown">{unknownText(model, center)}</span> : null}
          {outside > 0 ? <span class="chip">{outside} outside the scan</span> : null}
        </span>
      </div>
      <div class="siblings" style={place(layout.siblings)}>
        {layout.siblings.shown.map((symbol) => (
          <a key={symbol} class="pill" href={viewHref(View.Explore, symbol)} title={model.graph.symbols[symbol][1]}>
            {shortName(model, symbol)}
          </a>
        ))}
        <em>{layout.siblings.more > 0 ? `+${layout.siblings.more} in this module` : "same module"}</em>
      </div>
      {layout.unknown.map((card) => (
        <div key={`${card.row[1]}:${card.row[3]}`} class="lens-card unknown" style={place(card)}>
          <b>{card.row[1]}</b>
          <span class="meta">
            <ProofMark proof={Proof.Unknown} /> · {card.row[2]}
          </span>
        </div>
      ))}
    </>
  );
}

function Neighbors(props: { model: Model; title: string; list: readonly Link[]; owner: number; fromOther: boolean }) {
  const { model, list } = props;
  return (
    <Box title={`${props.title} · ${list.length}`} evidence={Evidence.Observed}>
      {list.length === 0 ? (
        <p class="more">none</p>
      ) : (
        <ul class="pairs">
          {list.slice(0, LIST_SHOWN).map((link) => (
            <li key={link.other}>
              <ProofMark proof={proofOf(link.partial)} />{" "}
              <a href={viewHref(View.Explore, link.other)}>{shortName(model, link.other)}</a>{" "}
              <span class="where">
                {tailPath(fileName(model, props.fromOther ? link.other : props.owner))}:{link.line}
              </span>
            </li>
          ))}
        </ul>
      )}
      {list.length > LIST_SHOWN ? <p class="more">+{list.length - LIST_SHOWN} more</p> : null}
    </Box>
  );
}

function Details(props: { model: Model; symbol: number }) {
  const { model, symbol } = props;
  const [, name, line, , text] = model.graph.symbols[symbol];
  const parts = locate(model, symbol);
  return (
    <>
      <Box title="Location">
        <p class="code">
          {parts.map((part) => part.label).join(" › ")}
          <br />
          {fileName(model, symbol)}:{line}
          <br />
          {text}
        </p>
      </Box>
      <Neighbors model={model} title="Called by" list={model.incoming[symbol]} owner={symbol} fromOther={true} />
      <Neighbors model={model} title="Calls" list={model.outgoing[symbol]} owner={symbol} fromOther={false} />
      {model.graph.symbols[symbol][6] > 0 ? (
        <Box title="Outside the scan">
          <p>
            {counted(model.graph.symbols[symbol][6], "call")} of {name} resolve to code outside the scan, such as the
            standard library. They are neither proven edges nor unknown.
          </p>
        </Box>
      ) : null}
      {model.unknown[symbol].length > 0 ? (
        <Box title={`Unknown calls · ${unknownText(model, symbol)}`}>
          <ul class="pairs">
            {model.unknown[symbol].map((row) => (
              <li key={`${row[1]}:${row[3]}`}>
                <ProofMark proof={Proof.Unknown} /> <b>{row[1]}</b> {row[2]}{" "}
                <span class="where">
                  {tailPath(fileName(model, symbol))}:{row[3]}
                </span>
              </li>
            ))}
          </ul>
          <p class="more">The analysis cannot name the target of {name}.</p>
        </Box>
      ) : null}
    </>
  );
}

/** One lens. The page keys it by the function, so the open group starts fresh. */
function LensPage(props: { model: Model; symbol: number; chat: ChatState }) {
  const { model, symbol } = props;
  const [open, setOpen] = useState<OpenGroup | null>(null);
  const layout = useMemo(() => layoutLens(model, symbol, open), [model, symbol, open]);
  const module = moduleIndex(model, symbol);
  const file = fileName(model, symbol).split("/").pop() ?? "";
  return (
    <Workbench
      model={model}
      where={{ level: Level.Function, id: symbol, pkg: null }}
      chat={props.chat}
      symbol={symbol}
      name="Explore"
      here={{
        name: model.graph.symbols[symbol][1],
        counts: `${counted(model.incoming[symbol].length, "caller")} · ${counted(model.outgoing[symbol].length, "callee")} · ${unknownText(model, symbol)}`,
        meaning: "The center is the function. Callers are on the left, callees on the right. Click a neighbor to move the lens.",
        up: viewHref(View.Module, module),
        upName: file,
      }}
      summary={`lens · 1 hop · ${model.incoming[symbol].length + model.outgoing[symbol].length} neighbors · ${unknownText(model, symbol)}`}
      canvas={{
        width: layout.width,
        height: layout.height,
        label: "Lens",
        fitKey: `${symbol}:${open?.group}:${open?.side}`,
        children: <Lens model={model} layout={layout} center={symbol} onOpen={setOpen} />,
      }}
      note="Module-level calls are not shown."
      details={<Details model={model} symbol={symbol} />}
    />
  );
}

export function Explore(props: { model: Model | null; symbol: number | null; chat: ChatState }) {
  const { model } = props;
  if (model === null) {
    return (
      <Page title="Explore" lead="No map yet. Overview shows the progress.">
        {null}
      </Page>
    );
  }
  const symbol = props.symbol !== null && props.symbol < model.graph.symbols.length ? props.symbol : model.start;
  if (symbol === null) {
    return (
      <Page title="Explore" lead="The snapshot holds no function.">
        {null}
      </Page>
    );
  }
  return <LensPage key={symbol} model={model} symbol={symbol} chat={props.chat} />;
}
