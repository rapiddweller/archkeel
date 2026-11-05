/** AD-290: the app shell: navigation, the legends, the contract state and the current view. */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { StudioState } from "./api";
import { ChatState, useChat } from "./chat";
import { NavItem, View, viewHref } from "./components";
import { Level, Model, Where, lensSymbol } from "./model";
import { Crumb, LocationBar, crumbsOf } from "./navigation";
import { startStore, useStudio } from "./store";
import { AgentKind, ContractState, ExploreState, SnapshotCompleteness } from "./vocabulary";
import { ComponentLevel } from "./views/component";
import { ArchMap } from "./views/map";
import { ModuleLevel } from "./views/module";
import { Explore } from "./views/explore";
import { NotBuilt } from "./views/not-built";
import { Briefing } from "./views/briefing";
import { Report } from "./views/report";
import { Stories } from "./views/story";

/** `planned` pages show in the nav, muted and not clickable. */
const NAV: readonly { view: View; name: string; planned?: boolean }[] = [
  { view: View.Overview, name: "Briefing" },
  { view: View.Map, name: "Architecture" },
  { view: View.Stories, name: "Stories" },
  { view: View.Impact, name: "Impact", planned: true },
  { view: View.Target, name: "Target / Diff", planned: true },
];
const VIEWS = new Map<string, View>([...Object.values(View), View.Report].map((view) => [view, view]));
/** The levels of the architecture, down to the lens, keep the Architecture item highlighted. */
const NAV_OF: Partial<Record<View, View>> = {
  [View.Component]: View.Map,
  [View.Module]: View.Map,
  [View.Explore]: View.Map,
  [View.Report]: View.Overview,
};

const CONTRACT: Record<ContractState, string> = {
  [ContractState.NOT_CONFIGURED]: "Contract: NOT CONFIGURED",
  [ContractState.INVALID]: "Contract: INVALID",
  [ContractState.CONFIGURED]: "Contract: CONFIGURED",
};

interface Route {
  /** Null when the URL names no page: the shell then picks the Map, else Overview. */
  readonly view: View | null;
  /** The function of `#/explore/<n>`, else null. */
  readonly symbol: number | null;
  /** The story of `#/stories/<id>`, else null. */
  readonly story: string | null;
  /** The package path of `#/component/<n>/<package>`, else null. */
  readonly pkg: string | null;
}

function readRoute(): Route {
  const [, head, tail, last] = location.hash.split("/");
  return {
    view: VIEWS.get(head) ?? null,
    symbol: tail !== undefined && /^\d+$/.test(tail) ? Number(tail) : null,
    story: tail !== undefined && /^[a-z0-9][a-z0-9-]*$/.test(tail) ? tail : null,
    pkg: last !== undefined && /^[A-Za-z0-9_.]+$/.test(last) ? last : null,
  };
}

function useRoute(): Route {
  const [route, setRoute] = useState(readRoute);
  useEffect(() => {
    const listener = (): void => setRoute(readRoute());
    addEventListener("hashchange", listener);
    return () => removeEventListener("hashchange", listener);
  }, []);
  return route;
}

const isIndex = (value: number | null, size: number): value is number => value !== null && value < size;

function content(view: View, route: Route, state: StudioState, model: Model | null, chat: ChatState) {
  switch (view) {
    case View.Overview:
      return <Briefing state={state} model={model} chat={chat} />;
    case View.Map:
      return <ArchMap model={model} contract={state.contract} chat={chat} />;
    case View.Component:
      return model !== null && isIndex(route.symbol, model.graph.components.length) ? (
        <ComponentLevel key={`${route.symbol}:${route.pkg}`} model={model} component={route.symbol} pkg={route.pkg} chat={chat} />
      ) : (
        <ArchMap model={model} contract={state.contract} chat={chat} />
      );
    case View.Module:
      return model !== null && isIndex(route.symbol, model.graph.modules.length) ? (
        <ModuleLevel key={route.symbol} model={model} module={route.symbol} chat={chat} />
      ) : (
        <ArchMap model={model} contract={state.contract} chat={chat} />
      );
    case View.Explore:
      return <Explore model={model} symbol={route.symbol} chat={chat} />;
    case View.Report:
      return <Report state={state} />;
    case View.Stories:
      return (
        <Stories
          id={route.story}
          state={state}
        />
      );
    case View.Impact:
      return <NotBuilt title="Change impact" today="Planned in issue #793." />;
    case View.Target:
      return (
        <NotBuilt
          title="Target and diff"
          today="Today: archkeel init drafts a contract and archkeel init --adopt adopts the code as it is. Studio never writes a contract without your click."
        />
      );
  }
}

const TITLES: Partial<Record<View, string>> = {
  [View.Overview]: "Briefing",
  [View.Report]: "Static report",
  [View.Stories]: "Stories",
  [View.Impact]: "Change impact",
  [View.Target]: "Target and diff",
};

/** The one location bar of every page: the architecture, then where this page is. */
function placeOf(view: View, route: Route, model: Model | null): { crumbs: readonly Crumb[]; current: string } {
  const root: Crumb = { label: "Architecture", href: viewHref(View.Map) };
  const where: Where | null =
    model === null
      ? null
      : view === View.Component && isIndex(route.symbol, model.graph.components.length)
        ? { level: Level.Component, id: route.symbol, pkg: route.pkg }
        : view === View.Module && isIndex(route.symbol, model.graph.modules.length)
          ? { level: Level.Module, id: route.symbol, pkg: null }
          : view === View.Explore
            ? { level: Level.Function, id: lensSymbol(model, route.symbol), pkg: null }
            : view === View.Map
              ? { level: Level.Map, id: null, pkg: null }
              : null;
  if (model !== null && where !== null) return crumbsOf(model, where);
  if (view === View.Stories && route.story !== null) {
    return { crumbs: [root, { label: "Stories", href: viewHref(View.Stories) }], current: route.story };
  }
  if (view === View.Map || view === View.Component || view === View.Module || view === View.Explore) {
    return { crumbs: [], current: "Architecture" };
  }
  return { crumbs: view === View.Overview ? [] : [root], current: TITLES[view] ?? "" };
}

/** The levels fill the main area; the other pages scroll. */
const FULL: ReadonlySet<View> = new Set([View.Map, View.Component, View.Module, View.Explore]);

function Shell() {
  const route = useRoute();
  const { state, error, model } = useStudio();
  const chat = useChat(
    state?.agent ?? AgentKind.CLAUDE,
    state?.explore === ExploreState.INCOMPLETE
      ? SnapshotCompleteness.INCOMPLETE
      : SnapshotCompleteness.COMPLETE,
  );
  const view = route.view ?? (state?.explore === ExploreState.DONE ? View.Map : View.Overview);
  return (
    <>
      <aside>
        <div class="brand">
          ARCHKEEL<small>STUDIO{state ? ` · ${state.root_name}` : ""}</small>
        </div>
        <p class="label">Workspace</p>
        <nav aria-label="Workspace">
          {NAV.map((item) =>
            item.planned ? (
              <span key={item.view} class="planned" title="not built yet" aria-disabled="true">
                {item.name} <small>Planned</small>
              </span>
            ) : (
              <NavItem key={item.view} href={viewHref(item.view)} current={item.view === (NAV_OF[view] ?? view)}>
                {item.name}
              </NavItem>
            ),
          )}
        </nav>
        <p class="label">Contract</p>
        <p class="contract">{state ? CONTRACT[state.contract] : "Contract: …"}</p>
        <p class="secondary">
          <a href={viewHref(View.Report)} aria-current={view === View.Report ? "page" : undefined}>
            Open the static report
          </a>
          <small>The page that CI and Pages publish. It keeps its own look.</small>
        </p>
      </aside>
      <main class={FULL.has(view) ? "full" : undefined}>
        <header class="titlebar">
          <LocationBar {...placeOf(view, route, model)} />
        </header>
        <div class="page">
          {error ? <p role="alert">{error}</p> : null}
          {state ? content(view, route, state, model, chat) : <p>Reading the Studio state…</p>}
        </div>
      </main>
    </>
  );
}

const app = document.getElementById("app");
if (app) {
  startStore();
  render(<Shell />, app);
}
