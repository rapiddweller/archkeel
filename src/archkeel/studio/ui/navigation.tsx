/** AD-290: where am I: the structure tree, the location bar and the search. Props only. */
import { useEffect, useRef, useState } from "preact/hooks";
import { View, viewHref } from "./components";
import {
  Level,
  Model,
  TreeNode,
  Where,
  trail,
  fileName,
  fileOf,
  fullName,
  moduleKey,
  moduleIndex,
  search,
  symbolKey,
  tailPath,
} from "./model";

const FUNCTIONS_SHOWN = 60;
const INDENT = 12;

function Modules(props: { model: Model; node: TreeNode; depth: number } & TreeProps) {
  const { model, node, depth } = props;
  return (
    <>
      {[...node.modules]
        .sort((a, b) => model.graph.modules[a][0].localeCompare(model.graph.modules[b][0]))
        .map((module) => {
          const key = moduleKey(module);
          const open = props.open.has(key);
          const functions = [...model.members[module]].sort(
            (a, b) => model.graph.symbols[a][2] - model.graph.symbols[b][2],
          );
          const file = fileOf(model, module);
          return (
            <div key={key}>
              <button
                type="button"
                class="tn module"
                aria-expanded={open}
                style={{ paddingLeft: `${depth * INDENT}px` }}
                title={model.graph.modules[module][0]}
                onClick={() => props.onToggle(key)}
              >
                <span class="disclosure" aria-hidden="true">
                  {open ? "▾" : "▸"}
                </span>
                <span class="nm">{file}</span>
                <span class="ct">{functions.length}</span>
              </button>
              {open
                ? functions.slice(0, FUNCTIONS_SHOWN).map((symbol) => (
                    <a
                      key={symbolKey(symbol)}
                      class="tn fn"
                      href={viewHref(View.Explore, symbol)}
                      aria-current={symbol === props.current ? "location" : undefined}
                      style={{ paddingLeft: `${(depth + 1) * INDENT + 8}px` }}
                      title={fullName(model, symbol)}
                    >
                      <span class="nm">{model.graph.symbols[symbol][1]}</span>
                    </a>
                  ))
                : null}
              {open && functions.length > FUNCTIONS_SHOWN ? (
                <p class="tn more" style={{ paddingLeft: `${(depth + 1) * INDENT + 8}px` }}>
                  +{functions.length - FUNCTIONS_SHOWN} more
                </p>
              ) : null}
            </div>
          );
        })}
    </>
  );
}

interface TreeProps {
  readonly open: ReadonlySet<string>;
  readonly current: number | null;
  readonly onToggle: (key: string) => void;
}

function Branch(props: { model: Model; node: TreeNode; depth: number; component?: number } & TreeProps) {
  const { node, depth } = props;
  const open = props.open.has(node.key);
  return (
    <div>
      <button
        type="button"
        class={`tn folder${props.component === undefined ? "" : ` comp-${props.component % 10}`}`}
        aria-expanded={open}
        style={{ paddingLeft: `${depth * INDENT}px` }}
        onClick={() => props.onToggle(node.key)}
      >
        <span class="disclosure" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
        {props.component === undefined ? null : <span class="dot" aria-hidden="true" />}
        <span class="nm">{node.label}</span>
        <span class="ct">{node.count}</span>
      </button>
      {open ? (
        <>
          {node.kids.map((kid) => (
            <Branch {...props} key={kid.key} node={kid} depth={depth + 1} component={undefined} />
          ))}
          <Modules {...props} depth={depth + 1} />
        </>
      ) : null}
    </div>
  );
}

/** Component, package, module file and function; only the opened branches draw. */
export function StructureTree(props: { model: Model } & TreeProps) {
  return (
    <div class="tree">
      {props.model.tree.map((node, index) => (
        <Branch {...props} key={node.key} node={node} depth={0} component={index} />
      ))}
    </div>
  );
}

/** One step of the location bar: the place it names and where a click goes (one level up). */
export interface Crumb {
  readonly label: string;
  readonly href: string;
}

const LEVEL_VIEW: Record<Level, View> = {
  [Level.Map]: View.Map,
  [Level.Component]: View.Component,
  [Level.Module]: View.Module,
  [Level.Function]: View.Explore,
};

const whereHref = (where: Where): string =>
  where.id === null ? viewHref(View.Map) : viewHref(LEVEL_VIEW[where.level], where.id, where.pkg ?? undefined);

/** Architecture, component, packages, module file and function of a place, as links. */
export function crumbsOf(model: Model, where: Where): { crumbs: readonly Crumb[]; current: string } {
  const { parts, current } = trail(model, where);
  return {
    crumbs: parts.map((part) => ({ label: part.label, href: part.where ? whereHref(part.where) : viewHref(View.Map) })),
    current,
  };
}

/** The one location bar: the same place and look on every page; each part goes up to its level. */
export function LocationBar(props: { crumbs: readonly Crumb[]; current: string }) {
  return (
    <div class="location" role="navigation" aria-label="Location">
      {props.crumbs.map((crumb) => (
        <span key={crumb.href + crumb.label}>
          <a href={crumb.href}>{crumb.label}</a>
          <i aria-hidden="true">›</i>
        </span>
      ))}
      <b aria-current="location">{props.current}</b>
    </div>
  );
}

/** Search by function or module; Cmd/Ctrl+K focuses the field. */
export function SearchBox(props: { model: Model; onPick: (symbol: number) => void }) {
  const field = useRef<HTMLInputElement>(null);
  const [text, setText] = useState("");
  const [light, setLight] = useState(0);
  const found = search(props.model, text);
  useEffect(() => {
    const listener = (event: KeyboardEvent): void => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        field.current?.focus();
      }
    };
    addEventListener("keydown", listener);
    return () => removeEventListener("keydown", listener);
  }, []);
  const pick = (symbol: number): void => {
    setText("");
    props.onPick(symbol);
  };
  const arrows: Record<string, () => void> = {
    ArrowDown: () => setLight(Math.min(found.length - 1, light + 1)),
    ArrowUp: () => setLight(Math.max(0, light - 1)),
    Enter: () => found[light] !== undefined && pick(found[light]),
    Escape: () => {
      setText("");
      field.current?.blur();
    },
  };
  return (
    <div class="search">
      <input
        ref={field}
        type="search"
        role="combobox"
        aria-expanded={found.length > 0}
        aria-controls="search-results"
        aria-label="Search a function or module"
        placeholder="Search a function…"
        autoComplete="off"
        value={text}
        onInput={(event) => {
          setText(event.currentTarget.value);
          setLight(0);
        }}
        onKeyDown={(event) => arrows[event.key]?.()}
      />
      <kbd>⌘K</kbd>
      {text.trim().length >= 2 ? (
        <ul id="search-results" role="listbox" class="results">
          {found.map((symbol, index) => (
            <li
              key={symbol}
              role="option"
              aria-selected={index === light}
              class={index === light ? "light" : undefined}
              onMouseDown={(event) => {
                event.preventDefault();
                pick(symbol);
              }}
            >
              <span>{props.model.graph.symbols[symbol][1]}</span>
              <small>
                {props.model.graph.modules[moduleIndex(props.model, symbol)][3]} ·{" "}
                {tailPath(fileName(props.model, symbol))}:{props.model.graph.symbols[symbol][2]}
              </small>
            </li>
          ))}
          {found.length === 0 ? (
            <li role="option" aria-selected="false">
              <small>no match</small>
            </li>
          ) : null}
        </ul>
      ) : null}
    </div>
  );
}
