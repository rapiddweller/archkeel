/** AD-290: the shared page of every level: toolbar, structure tree, canvas, and a side panel that starts with "You are here". */
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";
import { ChatPanel, ChatState } from "./chat";
import { Box, ProofMark, View, viewHref } from "./components";
import { Proof, proofKind, proofOf } from "./evidence";
import { LevelBox, LevelLayout, LevelLink, LevelStub, cardKey, stubKey, tileKey } from "./level-layout";
import { makeRouter, midOf, roundedPath } from "./level-route";
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
  /** The module path of a function, or the file path of a module. */
  readonly path: string;
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

const TIP_MS = 400;
let tipTimer: number | undefined;
let tipBox: HTMLDivElement | null = null;

/** One compact tooltip for all cards (a name and a path): after 400 ms, below the card, so it never covers its own text. */
function showTip(card: Element, text: string, x: number): void {
  window.clearTimeout(tipTimer);
  tipTimer = window.setTimeout(() => {
    if (tipBox === null) {
      tipBox = document.createElement("div");
      tipBox.className = "tip";
      tipBox.setAttribute("role", "tooltip");
      document.body.append(tipBox);
    }
    tipBox.textContent = text;
    tipBox.hidden = false;
    const box = card.getBoundingClientRect();
    const below = box.bottom + 4;
    const fits = below + tipBox.offsetHeight < innerHeight;
    // Right of the pointer, below the card: the text of the card stays free.
    const left = Math.min(Math.max(8, x), innerWidth - tipBox.offsetWidth - 8);
    tipBox.style.left = `${left}px`;
    tipBox.style.top = `${fits ? below : Math.max(8, box.top - tipBox.offsetHeight - 4)}px`;
  }, TIP_MS);
}

function hideTip(): void {
  window.clearTimeout(tipTimer);
  if (tipBox !== null) tipBox.hidden = true;
}

const quiet = (): boolean => matchMedia("(prefers-reduced-motion: reduce)").matches;

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
    layout.tiles.forEach((tile) => found.set(tileKey(tile.label), tile));
    layout.stubs.forEach((stub) => found.set(stubKey(stub.side, stub.ref), stub));
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
  const dim = (key: string): string => (focus.key === null || key === focus.key || near.has(key) ? "" : " dim");
  const names = (stub: LevelStub): string[] => {
    const other = connected.find((item) => item.other === stubKey(stub.side, stub.ref));
    if (other === undefined) return [];
    return [...new Set(other.link.pairs.map((pair) => props.fnName(stub.side === Side.In ? pair.source : pair.target)))];
  };
  const calm = quiet();
  const tip = (key: string, text: string) => ({
    onMouseEnter: (event: MouseEvent) => {
      focus.over(key);
      if (event.currentTarget instanceof Element) showTip(event.currentTarget, text, event.clientX + 12);
    },
    onMouseLeave: () => {
      focus.over(null);
      hideTip();
    },
    onFocus: () => focus.over(key),
    onBlur: () => focus.over(null),
  });
  return (
    <>
      {layout.plates.map((plate) => (
        <div key={plate.label} class={`plate ${props.plate} comp-${props.colour(0) % 10}`} style={place(plate)}>
          <span>{tailName(plate.label, 38)}</span>
        </div>
      ))}
      <svg class="lines" width={layout.width} height={layout.height} aria-hidden="true">
        {focus.key === null
          ? layout.aggregates.map((line) => (
              <g key={line.key} class="aggregate">
                <path d={roundedPath(line.points)} />
                <circle cx={line.points[line.points.length - 1][0]} cy={line.points[line.points.length - 1][1]} r="2.5" />
              </g>
            ))
          : null}
        {lines.map(({ link, points }) => {
          const kind = link.claim > 0 ? "claim" : "proven";
          const far = link.a === focus.key ? link.b : link.a;
          const state = focus.line === null ? "" : focus.line === far ? " on" : " off";
          const d = roundedPath(points);
          const first = points[0];
          const last = points[points.length - 1];
          const mid = midOf(points);
          return (
            <g key={lineKey(link)} class={`focus-line ${kind}${state}`}>
              <path class="halo" d={d} />
              <path class="stroke" d={d} data-points={points.map((point) => point.join(",")).join(" ")} />
              <circle class="port" cx={first[0]} cy={first[1]} r="2.5" />
              <circle class="port" cx={last[0]} cy={last[1]} r="2.5" />
              {state === " off" ? null : calm ? (
                <path class="chevron" d="M-3.5 -3.5 L2.5 0 L-3.5 3.5" transform={`translate(${mid.x} ${mid.y}) rotate(${mid.angle})`} />
              ) : (
                <circle class="flow" r="3" style={{ offsetPath: `path("${d}")` }} />
              )}
            </g>
          );
        })}
      </svg>
      {[Side.In, Side.Out]
        .filter((side) => layout.stubs.some((stub) => stub.side === side))
        .map((side) => (
          <p key={side} class="head" style={{ left: `${side === Side.In ? layout.columns.in : layout.columns.out}px`, top: "8px" }}>
            {side === Side.In ? props.headIn : props.headOut}
          </p>
        ))}
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
            aria-pressed={focus.pinned === key}
            aria-label={info.title}
            onClick={(event) => {
              // A click pins the focus; Enter (no pointer) and a double click open the card.
              if (event.detail === 0 || event.metaKey || event.ctrlKey) return;
              event.preventDefault();
              if (event.detail === 1) focus.pin(focus.pinned === key ? null : key);
              else location.hash = info.href;
            }}
            {...tip(key, `${info.name}\n${info.path}`)}
          >
            <b>{info.name}</b>
            <span class="meta">{info.meta}</span>
          </a>
        );
      })}
      {layout.tiles.map((tile) => {
        const key = tileKey(tile.label);
        return (
          <button
            key={key}
            type="button"
            class={`lens-card tile${dim(key)}`}
            style={place(tile)}
            onClick={() => props.onOpen(tile.label)}
            {...tip(key, `${tile.label}\n+${tile.hidden} more, click to open`)}
          >
            <b>{tailName(tile.label, 24)}</b>
            <span class="meta">+{tile.hidden} more · open</span>
          </button>
        );
      })}
      {layout.stubs.map((stub) => {
        const info = props.stub(stub);
        const key = stubKey(stub.side, stub.ref);
        const chips = names(stub);
        return (
          <a key={key} class={`lens-card stub ${stub.claim > 0 ? "claim" : "proven"}${dim(key)}`} data-side={stub.side} data-drill style={place(stub)} href={info.href} aria-label={info.title} {...tip(key, `${info.name}\n${info.path}`)}>
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

export interface FocusItem {
  readonly name: string;
  readonly href: string;
  readonly where: string;
  readonly partial: boolean;
  /** `calls`, `called by` or `both`: the caller is the one that the dots start from. */
  readonly direction: string;
}
export interface FocusRow {
  /** The key of the far end; a row lights its line by it. */
  readonly key: string;
  readonly name: string;
  readonly href: string;
  readonly where: string;
  readonly tally: Tally;
  /** The row is itself one neighbor function. */
  readonly neighbor: boolean;
  /** The functions on the other side. */
  readonly items: readonly FocusItem[];
}

/** A path that wraps at its separators, so a name never breaks in the middle of a word. */
export function Breakable(props: { text: string }) {
  return (
    <>
      {props.text.split(/(?<=[./:·])/).map((part, index) => (
        <span key={index}>
          {part}
          <wbr />
        </span>
      ))}
    </>
  );
}

const ROWS_SHOWN = 10;

/** The side panel of a focus: each connected card with its module, file, line and proof; a row lights its line. */
export function FocusList(props: { focus: Focus; rows: readonly FocusRow[]; title: string; open: { href: string; label: string } | null }) {
  const { focus } = props;
  const [all, setAll] = useState(false);
  if (focus.key === null) {
    return (
      <Box title="Focus">
        <p class="more">Hover a card to see its lines. Click it to pin them; Esc clears. Dots show the direction of the call.</p>
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
      <p class="more">Dots show the direction of the call: from the caller to the callee.</p>
      {props.rows.length === 0 ? <p class="more">No call to or from a card of this page.</p> : null}
      <ul class="pairs focus-rows">
        {(all ? props.rows : props.rows.slice(0, ROWS_SHOWN)).map((row) => {
          const items = row.items.filter((item) => item.name !== row.name || !row.neighbor);
          return (
            <li key={row.key + row.name} data-neighbor={row.neighbor ? "" : undefined} onMouseEnter={() => focus.light(row.key)} onMouseLeave={() => focus.light(null)}>
              <a href={row.href}>{row.name}</a>{" "}
              <span class="where">
                <Breakable text={row.where} />
              </span>
              <br />
              <Counts tally={row.tally} />
              {items.slice(0, 6).map((item) => (
                <span key={item.href + item.name} class="where item" data-neighbor="">
                  <br />
                  <ProofMark proof={proofOf(item.partial)} /> <a href={item.href}>{item.name}</a> {item.direction} <Breakable text={item.where} />
                </span>
              ))}
              {items.length > 6 ? <span class="where"> +{items.length - 6} more</span> : null}
            </li>
          );
        })}
      </ul>
      {props.rows.length > ROWS_SHOWN ? (
        <button type="button" class="toggle" aria-expanded={all} onClick={() => setAll(!all)}>
          {all ? "Show fewer" : `Show all ${props.rows.length}`}
        </button>
      ) : null}
    </Box>
  );
}

/** The rows of the side panel for a focused card or stub: each connected box with the functions on the other side. */
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
    neighbor: false,
    items: link.pairs.map((pair) => {
      const symbol = outgoing ? pair.target : pair.source;
      return {
        name: shortName(model, symbol),
        href: viewHref(View.Explore, symbol),
        where: `${fileName(model, symbol).split("/").pop()}:${model.graph.symbols[symbol][2]} · ${fullName(model, symbol)}`,
        partial: pair.partial,
        direction: outgoing ? "called" : "calls it",
      };
    }),
  }));
}

/** The rows for a focused function: every distinct neighbor, those of this module one each, the others grouped by module. */
export function functionRows(model: Model, symbol: number, module: number): FocusRow[] {
  const found = new Map<number, { out: boolean; into: boolean; partial: boolean; line: number }>();
  for (const link of model.outgoing[symbol]) found.set(link.other, { out: true, into: false, partial: link.partial, line: link.line });
  for (const link of model.incoming[symbol]) {
    const known = found.get(link.other);
    found.set(link.other, { out: known?.out ?? false, into: true, partial: (known?.partial ?? false) || link.partial, line: known?.line ?? link.line });
  }
  const direction = (entry: { out: boolean; into: boolean }): string => (entry.out && entry.into ? "calls and is called by" : entry.out ? "is called by this" : "calls this");
  const rows: FocusRow[] = [];
  const groups = new Map<number, FocusItem[]>();
  const tallies = new Map<number, { proven: number; claim: number }>();
  for (const [other, entry] of found) {
    const where = `${fileName(model, other).split("/").pop()}:${model.graph.symbols[other][2]}`;
    const home = model.graph.symbols[other][0];
    const item: FocusItem = { name: shortName(model, other), href: viewHref(View.Explore, other), where, partial: entry.partial, direction: direction(entry) };
    if (home === module) {
      rows.push({ key: cardKey(Level.Function, other), name: item.name, href: item.href, where: `${item.direction} · ${where}`, tally: entry.partial ? { proven: 0, claim: 1 } : { proven: 1, claim: 0 }, neighbor: true, items: [] });
    } else {
      groups.set(home, [...(groups.get(home) ?? []), item]);
      const now = tallies.get(home) ?? { proven: 0, claim: 0 };
      tallies.set(home, { proven: now.proven + (entry.partial ? 0 : 1), claim: now.claim + (entry.partial ? 1 : 0) });
    }
  }
  groups.forEach((items, home) => {
    const side = items.some((item) => item.direction !== "is called by this") ? Side.In : Side.Out;
    rows.push({
      key: stubKey(side, `${home}`),
      name: model.graph.modules[home][1].split("/").pop() ?? "",
      href: viewHref(View.Module, home),
      where: model.graph.modules[home][0],
      tally: tallies.get(home) as Tally,
      neighbor: false,
      items,
    });
  });
  return rows;
}
