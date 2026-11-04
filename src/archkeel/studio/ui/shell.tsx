/** AD-290: the app shell: navigation, the legends, the contract state and the current view. */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { StudioState } from "./api";
import { ChatState, useChat } from "./chat";
import { Legend, NavItem, ProofLegend, View, viewHref } from "./components";
import { Model } from "./model";
import { startStore, useStudio } from "./store";
import { ContractState, ExploreState } from "./vocabulary";
import { ArchMap } from "./views/map";
import { Explore } from "./views/explore";
import { NotBuilt } from "./views/not-built";
import { Overview } from "./views/overview";
import { Report } from "./views/report";
import { Stories } from "./views/story";

const NAV: readonly { view: View; name: string }[] = [
  { view: View.Overview, name: "Overview" },
  { view: View.Map, name: "Map" },
  { view: View.Explore, name: "Explore" },
  { view: View.Report, name: "Report" },
  { view: View.Stories, name: "Stories" },
  { view: View.Impact, name: "Impact" },
  { view: View.Target, name: "Target / Diff" },
];
const VIEWS = new Map<string, View>(NAV.map((item) => [item.view, item.view]));

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
}

function readRoute(): Route {
  const [, head, tail] = location.hash.split("/");
  return {
    view: VIEWS.get(head) ?? null,
    symbol: tail !== undefined && /^\d+$/.test(tail) ? Number(tail) : null,
    story: tail !== undefined && /^[a-z0-9][a-z0-9-]*$/.test(tail) ? tail : null,
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

function content(view: View, route: Route, state: StudioState, model: Model | null, chat: ChatState) {
  switch (view) {
    case View.Overview:
      return <Overview state={state} />;
    case View.Map:
      return <ArchMap model={model} contract={state.contract} chat={chat} />;
    case View.Explore:
      return <Explore model={model} symbol={route.symbol} chat={chat} />;
    case View.Report:
      return <Report state={state} />;
    case View.Stories:
      return <Stories id={route.story} ready={state.explore === ExploreState.DONE} />;
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

/** The Map and Explore fill the main area; the other pages scroll. */
const FULL: ReadonlySet<View> = new Set([View.Map, View.Explore]);

function Shell() {
  const route = useRoute();
  const { state, error, model } = useStudio();
  const chat = useChat();
  const view = route.view ?? (state?.explore === ExploreState.DONE ? View.Map : View.Overview);
  return (
    <>
      <aside>
        <div class="brand">
          ARCHKEEL<small>STUDIO{state ? ` · ${state.root_name}` : ""}</small>
        </div>
        <p class="label">Workspace</p>
        <nav aria-label="Workspace">
          {NAV.map((item) => (
            <NavItem key={item.view} href={viewHref(item.view)} current={item.view === view}>
              {item.name}
            </NavItem>
          ))}
        </nav>
        <p class="label">Evidence model</p>
        <Legend />
        <p class="label">Calls</p>
        <ProofLegend />
        <p class="label">Contract</p>
        <p class="contract">{state ? CONTRACT[state.contract] : "Contract: …"}</p>
      </aside>
      <main class={FULL.has(view) ? "full" : undefined}>
        {error ? <p role="alert">{error}</p> : null}
        {state ? content(view, route, state, model, chat) : <p>Reading the Studio state…</p>}
      </main>
    </>
  );
}

const app = document.getElementById("app");
if (app) {
  startStore();
  render(<Shell />, app);
}
