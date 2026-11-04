/** AD-290: the shared page of every level: toolbar, structure tree, canvas, and a side panel that starts with "You are here". */
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { ChatPanel, ChatState } from "./chat";
import { Box, View, viewHref } from "./components";
import { Proof, proofKind } from "./evidence";
import { LevelLayout, LevelStub, cardKey, stubKey } from "./level-layout";
import { Side } from "./lens-layout";
import { Level, Model, Tally, Where, compact, opened } from "./model";
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
  // Esc goes one level up; a text field keeps its own Esc.
  useEffect(() => {
    const listener = (event: KeyboardEvent): void => {
      if (event.key !== "Escape" || here.up === null || event.target instanceof HTMLInputElement) return;
      location.hash = here.up;
    };
    addEventListener("keydown", listener);
    return () => removeEventListener("keydown", listener);
  }, [here.up]);
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

export interface CardInfo {
  readonly href: string;
  readonly name: string;
  /** The full text for the tooltip. */
  readonly title: string;
  readonly meta: ComponentChildren;
}

export interface StubInfo {
  readonly href: string;
  readonly name: string;
  readonly title: string;
}

const place = (box: { x: number; y: number; width: number; height: number }): Record<string, string> => ({
  left: `${box.x}px`,
  top: `${box.y}px`,
  width: `${box.width}px`,
  height: `${box.height}px`,
});

/** The drawing of the modules of a component or the functions of a module, with the stubs at its sides. */
export function LevelCanvas(props: {
  layout: LevelLayout;
  level: Level;
  card: (index: number) => CardInfo;
  stub: (stub: LevelStub) => StubInfo;
  colour: (index: number) => number;
  headIn: string;
  headOut: string;
}) {
  const { layout, level } = props;
  const [hot, setHot] = useState<string | null>(null);
  const keyOf = (stub: LevelStub): string => stubKey(stub.side, stub.id);
  const lit = (a: string, b: string): boolean => hot !== null && (a === hot || b === hot);
  const headX = (side: Side): number => (layout.stubs.find((stub) => stub.side === side)?.x ?? 0);
  return (
    <>
      {layout.plates.map((plate) => (
        <div key={plate.label} class={`plate comp-${props.colour(0) % 10}`} style={place(plate)}>
          <span title={plate.label}>{plate.label}</span>
        </div>
      ))}
      <svg class="lines" width={layout.width} height={layout.height} aria-hidden="true">
        {layout.lines.map((line) => {
          const kind = line.claim > 0 ? "claim" : "proven";
          const state = hot === null ? (line.strong ? "strong" : "faint") : lit(line.a, line.b) ? "lit" : "dim";
          return <path key={`${line.a}|${line.b}`} class={`link ${kind} ${state}`} d={line.path} stroke-width={line.width} />;
        })}
      </svg>
      {layout.lines
        .filter((line) => line.strong && line.proven + line.claim > 1 && layout.lines.length < 40)
        .map((line) => (
          <span key={`n:${line.a}|${line.b}`} class={`count${line.claim > 0 ? " claim" : ""}`} style={{ left: `${line.middle[0]}px`, top: `${line.middle[1]}px` }}>
            {compact(line.proven + line.claim)} {line.claim > 0 ? "✎" : "✓"}
          </span>
        ))}
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
            class={`lens-card level-card comp-${props.colour(card.index) % 10}`}
            data-drill
            style={place(card)}
            href={info.href}
            title={info.title}
            onMouseEnter={() => setHot(key)}
            onMouseLeave={() => setHot(null)}
            onFocus={() => setHot(key)}
            onBlur={() => setHot(null)}
          >
            <b>{info.name}</b>
            <span class="meta">{info.meta}</span>
          </a>
        );
      })}
      {layout.stubs.map((stub) => {
        const info = props.stub(stub);
        return (
          <a
            key={keyOf(stub)}
            class={`lens-card stub ${stub.claim > 0 ? "claim" : "proven"}`}
            data-drill
            style={place(stub)}
            href={info.href}
            title={info.title}
            onMouseEnter={() => setHot(keyOf(stub))}
            onMouseLeave={() => setHot(null)}
            onFocus={() => setHot(keyOf(stub))}
            onBlur={() => setHot(null)}
          >
            <b>{info.name}</b>
            <span class="meta">
              <Counts tally={stub} />
            </span>
          </a>
        );
      })}
      {layout.more.stubs + layout.more.cards > 0 ? (
        <p class="lens-card more" style={{ left: "0px", top: `${layout.height - 34}px`, width: "420px", height: "28px" }}>
          +{layout.more.stubs} more stubs, +{layout.more.cards} more functions not drawn
        </p>
      ) : null}
    </>
  );
}
