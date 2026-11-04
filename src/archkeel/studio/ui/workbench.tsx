/** AD-290: the shared page of every level: toolbar, structure tree, canvas, and a side panel that starts with "You are here". */
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { ChatPanel, ChatState } from "./chat";
import { Box, ProofMark, View, viewHref } from "./components";
import { Proof, proofKind, proofOf } from "./evidence";
import { LevelBox, LevelLayout, LevelLink, LevelStub, cardKey, stubKey } from "./level-layout";
import { makeRouter, roundedPath } from "./level-route";
import { Side } from "./lens-layout";
import { Level, Model, Tally, Where, compact, fileName, fullName, opened, shortName, tailName } from "./model";
import { SearchBox, StructureTree } from "./navigation";
import { Viewport } from "./viewport";

/** Proven and claim call sites apart, each with its glyph and word. */
export function Counts(props: { tally: Tally }) {
  const { proven, claim } = props.tally;
  const mark = (proof: Proof, count: number) => (
    <>
      {compact(count)} <span aria-hidden="true">{proofKind(proof).glyph}</span> {proofKind(proof).word}
    </>
  );
  return (
    <>
      {proven > 0 || claim === 0 ? mark(Proof.Proven, proven) : null}
      {proven > 0 && claim > 0 ? " · " : null}
      {claim > 0 ? mark(Proof.Claim, claim) : null}
    </>
  );
}

/** What the reader needs to place a level: its name, its numbers, what a card means, and the way up. */
export interface Here {
  readonly name: string;
  readonly counts: string;
  readonly meaning: string;
  readonly up: string | null;
  readonly upName: string | null;
}

const DEPTH: Record<Level, number> = { [Level.Map]: 1, [Level.Component]: 2, [Level.Module]: 3, [Level.Function]: 4 };
const ZOOM_MS = 250;
const ZOOM_FROM = 0.3;
// The level and the clicked card of the last page: a drill zooms in from the card, going up zooms out.
let lastLevel: Level | null = null;
let clicked: { readonly x: number; readonly y: number } | null = null;

const treeOpen = (): boolean => matchMedia("(min-width: 1500px)").matches;
const detailsOpen = (): boolean => matchMedia("(min-width: 1300px)").matches;

export function Workbench(props: {
  model: Model;
  where: Where;
  chat: ChatState;
  /** The function that the chat takes as context, and the tree marks as the current one. */
  symbol: number | null;
  /** The side panel opens when this changes (a selected line shows its calls). */
  reveal?: unknown;
  /** A pinned card: Esc clears it before it goes up a level. */
  focus?: { readonly active: boolean; readonly clear: () => void };
  here: Here;
  /** The heading of the toolbar; the location bar above names the place. */
  name: string;
  summary: ComponentChildren;
  toolbar?: ComponentChildren;
  canvas: { readonly width: number; readonly height: number; readonly label: string; readonly fitKey: unknown; readonly children: ComponentChildren };
  note?: string;
  details: ComponentChildren;
}) {
  const { model, where, here } = props;
  const [asking, setAsking] = useState(false);
  const [tree, setTree] = useState(treeOpen);
  const [side, setSide] = useState(detailsOpen);
  const [open, setOpen] = useState<ReadonlySet<string>>(() => opened(model, where));
  const canvas = useRef<HTMLElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (!first.current && props.reveal !== null && props.reveal !== undefined) {
      setAsking(false);
      setSide(true);
    }
    first.current = false;
  }, [props.reveal]);
  const toggle = (key: string): void => {
    const next = new Set(open);
    if (!next.delete(key)) next.add(key);
    setOpen(next);
  };
  // Esc goes one level up; a text field keeps its own Esc. Set before the browser paints.
  useLayoutEffect(() => {
    const listener = (event: KeyboardEvent): void => {
      if (event.key !== "Escape" || event.target instanceof HTMLInputElement) return;
      if (props.focus?.active) props.focus.clear();
      else if (here.up !== null) location.hash = here.up;
    };
    addEventListener("keydown", listener);
    return () => removeEventListener("keydown", listener);
  }, [here.up, props.focus?.active]);
  useLayoutEffect(() => {
    const element = canvas.current;
    if (element === null) return;
    const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const before = lastLevel;
    lastLevel = where.level;
    const direction = before === null || before === where.level ? "none" : DEPTH[where.level] > DEPTH[before] ? "in" : "out";
    const state = reduced ? "none" : direction;
    element.dataset.transition = state;
    if (state !== "none" && typeof element.animate === "function") {
      const box = element.getBoundingClientRect();
      const from = clicked ?? { x: box.width / 2, y: box.height / 2 };
      const origin = `${from.x}px ${from.y}px`;
      element.animate(
        state === "in"
          ? [{ transform: `scale(${ZOOM_FROM})`, opacity: 0.2, transformOrigin: origin }, { transform: "scale(1)", opacity: 1, transformOrigin: origin }]
          : [{ transform: "scale(1.2)", opacity: 0.2 }, { transform: "scale(1)", opacity: 1 }],
        { duration: ZOOM_MS, easing: "ease-out" },
      );
    }
    clicked = null;
  }, []);
  return (
    <div class="workbench" data-tree={tree} data-details={side}>
      <header class="toolbar">
        <button type="button" class="toggle" aria-pressed={tree} onClick={() => setTree(!tree)}>
          Structure
        </button>
        <h1>{props.name}</h1>
        <SearchBox model={model} onPick={(picked) => (location.hash = viewHref(View.Explore, picked))} />
        {props.toolbar}
        <span class="summary">{props.summary}</span>
        <button
          type="button"
          class="toggle"
          aria-pressed={asking}
          onClick={() => {
            setAsking(!asking);
            setSide(true);
          }}
        >
          Ask
        </button>
        <button type="button" class="toggle" aria-pressed={side && !asking} onClick={() => (asking ? setAsking(false) : setSide(!side))}>
          Details
        </button>
      </header>
      <div class="structure" role="navigation" aria-label="Structure">
        <p class="label">Structure</p>
        <StructureTree model={model} open={open} current={props.symbol} onToggle={toggle} />
      </div>
      <section
        class="canvas"
        ref={canvas}
        onClickCapture={(event) => {
          const card = event.target instanceof Element ? event.target.closest("[data-drill]") : null;
          const area = canvas.current?.getBoundingClientRect();
          if (card === null || area === undefined) return;
          const box = card.getBoundingClientRect();
          clicked = { x: box.left + box.width / 2 - area.left, y: box.top + box.height / 2 - area.top };
        }}
      >
        <Viewport width={props.canvas.width} height={props.canvas.height} label={props.canvas.label} fitKey={props.canvas.fitKey}>
          {props.canvas.children}
        </Viewport>
        {props.note ? <p class="note">{props.note}</p> : null}
      </section>
      <aside class="details" aria-label={asking ? "Ask the agent" : "Details"}>
        <Box title="You are here">
          <p class="here-name">
            <b>{here.name}</b>
          </p>
          <p>{here.counts}</p>
          <p class="more">{here.meaning}</p>
          {here.up === null ? null : (
            <a class="toggle up" href={here.up}>
              ↑ Up to {here.upName} <kbd>Esc</kbd>
            </a>
          )}
        </Box>
        {asking ? <ChatPanel model={model} symbol={props.symbol} chat={props.chat} /> : props.details}
      </aside>
    </div>
  );
}

/** What a card says: its name, the full text for the tooltip, and a line of numbers. */
export interface CardInfo {
  readonly href: string;
  readonly name: string;
  readonly title: string;
  readonly meta: ComponentChildren;
}

export interface StubInfo {
  readonly href: string;
  readonly name: string;
  readonly title: string;
  /** The end of the module path, or the responsibility of a component. */
  readonly path: string;
}

/** The focus of a level: a pinned card (click) or a hovered one, and a row of the side panel that lights one line. */
export interface Focus {
  readonly pinned: string | null;
  readonly hover: string | null;
  readonly line: string | null;
  readonly active: boolean;
  readonly key: string | null;
  readonly pin: (key: string | null) => void;
  readonly over: (key: string | null) => void;
  readonly light: (line: string | null) => void;
  readonly clear: () => void;
}

export function useFocus(): Focus {
  const [pinned, setPinned] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [line, setLine] = useState<string | null>(null);
  return {
    pinned,
    hover,
    line,
    active: pinned !== null,
    key: pinned ?? hover,
    pin: setPinned,
    over: setHover,
    light: setLine,
    clear: () => {
      setPinned(null);
      setLine(null);
    },
  };
}

export const lineKey = (link: LevelLink): string => `${link.a}|${link.b}`;

const place = (box: LevelBox): Record<string, string> => ({
  left: `${box.x}px`,
  top: `${box.y}px`,
  width: `${box.width}px`,
  height: `${box.height}px`,
});

const CHIPS = 4;

/** The links of the focused card; the other end of each. */
export function linksOf(layout: LevelLayout, key: string | null): readonly { link: LevelLink; other: string; outgoing: boolean }[] {
  if (key === null) return [];
  return layout.links
    .filter((link) => link.a === key || link.b === key)
    .map((link) => ({ link, other: link.a === key ? link.b : link.a, outgoing: link.a === key }));
}

/** The drawing of the modules of a component or the functions of a module, with the stubs at its sides. Calm at rest. */
export function LevelCanvas(props: {
  layout: LevelLayout;
  level: Level;
  focus: Focus;
  card: (index: number) => CardInfo;
  stub: (stub: LevelStub) => StubInfo;
  /** The name of a function on the other side of a stub. */
  fnName: (symbol: number) => string;
  colour: (index: number) => number;
  plate: "package" | "module";
  headIn: string;
  headOut: string;
  onOpen: (label: string) => void;
}) {
  const { layout, level, focus } = props;
  const route = useMemo(() => makeRouter(layout), [layout]);
  const boxes = useMemo(() => {
    const found = new Map<string, LevelBox>();
    layout.cards.forEach((card) => found.set(cardKey(level, card.index), card));
    layout.stubs.forEach((stub) => found.set(stubKey(stub.side, stub.id), stub));
    return found;
  }, [layout, level]);
  const connected = linksOf(layout, focus.key);
  const near = new Set(connected.map((item) => item.other));
  const lines = useMemo(
    () =>
      connected.flatMap(({ link }) => {
        const from = boxes.get(link.a);
        const to = boxes.get(link.b);
        const points = from && to ? route(from, to) : null;
        return points ? [{ link, points }] : [];
      }),
    [layout, focus.key],
  );
  const headX = (side: Side): number => layout.stubs.find((stub) => stub.side === side)?.x ?? 0;
  const dim = (key: string): string => (focus.key === null || key === focus.key || near.has(key) ? "" : " dim");
  const names = (stub: LevelStub): string[] => {
    const other = connected.find((item) => item.other === stubKey(stub.side, stub.id));
    if (other === undefined) return [];
    return [...new Set(other.link.pairs.map((pair) => props.fnName(stub.side === Side.In ? pair.source : pair.target)))];
  };
  return (
    <>
      {layout.plates.map((plate) => (
        <div key={plate.label} class={`plate ${props.plate} comp-${props.colour(0) % 10}`} style={place(plate)}>
          <span title={plate.label}>{tailName(plate.label, 38)}</span>
        </div>
      ))}
      <svg class="lines" width={layout.width} height={layout.height} aria-hidden="true">
        {lines.map(({ link, points }) => {
          const kind = link.claim > 0 ? "claim" : "proven";
          const state = focus.line === null ? "" : focus.line === lineKey(link) ? " on" : " off";
          const d = roundedPath(points);
          return (
            <g key={lineKey(link)} class={`focus-line ${kind}${state}`}>
              <path class="halo" d={d} />
              <path class="stroke" d={d} data-points={points.map((point) => point.join(",")).join(" ")} />
            </g>
          );
        })}
      </svg>
      {layout.stubs.length > 0 ? (
        <>
          <p class="head" style={{ left: `${headX(Side.In)}px`, top: "4px" }}>
            {props.headIn}
          </p>
          <p class="head" style={{ left: `${headX(Side.Out)}px`, top: "4px" }}>
            {props.headOut}
          </p>
        </>
      ) : null}
      {layout.cards.map((card) => {
        const info = props.card(card.index);
        const key = cardKey(level, card.index);
        return (
          <a
            key={key}
            class={`lens-card level-card comp-${props.colour(card.index) % 10}${dim(key)}${focus.pinned === key ? " pinned" : ""}`}
            data-drill
            style={place(card)}
            href={info.href}
            title={info.title}
            aria-pressed={focus.pinned === key}
            onClick={(event) => {
              // A click pins the focus; Enter (no pointer) and a double click open the card.
              if (event.detail === 0 || event.metaKey || event.ctrlKey) return;
              event.preventDefault();
              if (event.detail === 1) focus.pin(focus.pinned === key ? null : key);
              else location.hash = info.href;
            }}
            onMouseEnter={() => focus.over(key)}
            onMouseLeave={() => focus.over(null)}
            onFocus={() => focus.over(key)}
            onBlur={() => focus.over(null)}
          >
            <b>{info.name}</b>
            <span class="meta">{info.meta}</span>
          </a>
        );
      })}
      {layout.tiles.map((tile) => (
        <button key={tile.label} type="button" class="lens-card tile" style={place(tile)} onClick={() => props.onOpen(tile.label)}>
          <b>+{tile.hidden} more</b>
          <span class="meta">open</span>
        </button>
      ))}
      {layout.stubs.map((stub) => {
        const info = props.stub(stub);
        const key = stubKey(stub.side, stub.id);
        const chips = names(stub);
        return (
          <a
            key={key}
            class={`lens-card stub ${stub.claim > 0 ? "claim" : "proven"}${dim(key)}`}
            data-drill
            style={place(stub)}
            href={info.href}
            title={info.title}
            onMouseEnter={() => focus.over(key)}
            onMouseLeave={() => focus.over(null)}
            onFocus={() => focus.over(key)}
            onBlur={() => focus.over(null)}
          >
            <b>{info.name}</b>
            <span class="meta path">{info.path}</span>
            <span class="meta">
              <Counts tally={stub} />
            </span>
            <span class="meta names">
              {chips.slice(0, CHIPS).join(" · ")}
              {chips.length > CHIPS ? ` +${chips.length - CHIPS}` : ""}
            </span>
          </a>
        );
      })}
      {layout.moreStubs > 0 ? (
        <p class="lens-card more" style={{ left: "0px", top: `${layout.height - 30}px`, width: "340px", height: "26px" }}>
          +{layout.moreStubs} more stubs not drawn
        </p>
      ) : null}
    </>
  );
}

export interface FocusRow {
  readonly key: string;
  readonly name: string;
  readonly href: string;
  readonly where: string;
  readonly tally: Tally;
  /** The functions on the other side: name, link to the lens, file and line. */
  readonly items: readonly { readonly name: string; readonly href: string; readonly where: string; readonly partial: boolean }[];
  readonly line: string;
}

/** The side panel of a focus: each connected card with its module, file, line and proof; a row lights its line. */
export function FocusList(props: { focus: Focus; rows: readonly FocusRow[]; title: string; open: { href: string; label: string } | null }) {
  const { focus } = props;
  if (focus.key === null) {
    return (
      <Box title="Focus">
        <p class="more">Hover a card to see its lines. Click it to pin them; Esc clears.</p>
      </Box>
    );
  }
  return (
    <Box title={`Focus · ${props.title}`}>
      {props.open === null ? null : (
        <p>
          <a class="toggle" href={props.open.href}>
            {props.open.label}
          </a>
        </p>
      )}
      {props.rows.length === 0 ? <p class="more">No call to or from a card of this page.</p> : null}
      <ul class="pairs focus-rows">
        {props.rows.map((row) => (
          <li key={row.key} onMouseEnter={() => focus.light(row.line)} onMouseLeave={() => focus.light(null)}>
            <a href={row.href}>{row.name}</a> <span class="where">{row.where}</span>
            <br />
            <Counts tally={row.tally} />
            {row.items
              .filter((item) => item.name !== row.name)
              .slice(0, 6)
              .map((item) => (
              <span key={item.href + item.name} class="where item">
                <br />
                <ProofMark proof={proofOf(item.partial)} /> <a href={item.href}>{item.name}</a> {item.where}
              </span>
            ))}
            {row.items.filter((item) => item.name !== row.name).length > 6 ? (
              <span class="where"> +{row.items.filter((item) => item.name !== row.name).length - 6} more</span>
            ) : null}
          </li>
        ))}
      </ul>
    </Box>
  );
}

/** The rows of the side panel for a focused card: each connected card with the functions on the other side. */
export function focusRows(
  model: Model,
  layout: LevelLayout,
  key: string | null,
  other: (key: string) => { readonly name: string; readonly href: string; readonly where: string },
): FocusRow[] {
  return linksOf(layout, key).map(({ link, other: far, outgoing }) => ({
    key: far,
    ...other(far),
    tally: link,
    line: lineKey(link),
    items: link.pairs.map((pair) => {
      const symbol = outgoing ? pair.target : pair.source;
      return {
        name: shortName(model, symbol),
        href: viewHref(View.Explore, symbol),
        where: `${fileName(model, symbol).split("/").pop()}:${model.graph.symbols[symbol][2]} · ${fullName(model, symbol)}`,
        partial: pair.partial,
      };
    }),
  }));
}
