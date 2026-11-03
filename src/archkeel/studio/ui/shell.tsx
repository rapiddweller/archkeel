/** AD-290: the app shell: navigation, the legend, the contract state and the current view. */
import { render } from "preact";
import { useEffect, useState } from "preact/hooks";
import { ContractState, StudioState } from "./api";
import { Legend, NavItem } from "./components";
import { startStore, useStudio } from "./store";
import { Explore } from "./views/explore";
import { NotBuilt } from "./views/not-built";
import { Overview } from "./views/overview";

const View = {
  Overview: "overview",
  Explore: "explore",
  Flows: "flows",
  Impact: "impact",
  Target: "target",
} as const;
type View = (typeof View)[keyof typeof View];

const NAV: readonly { view: View; name: string }[] = [
  { view: View.Overview, name: "Overview" },
  { view: View.Explore, name: "Explore" },
  { view: View.Flows, name: "Flows" },
  { view: View.Impact, name: "Impact" },
  { view: View.Target, name: "Target / Diff" },
];
const VIEWS = new Map(NAV.map((item) => [`#/${item.view}`, item.view]));

const CONTRACT: Record<ContractState, string> = {
  [ContractState.NotConfigured]: "Contract: NOT CONFIGURED",
  [ContractState.Invalid]: "Contract: INVALID",
  [ContractState.Configured]: "Contract: CONFIGURED",
};

function content(view: View, state: StudioState) {
  switch (view) {
    case View.Overview:
      return <Overview state={state} />;
    case View.Explore:
      return <Explore state={state} />;
    case View.Flows:
      return (
        <NotBuilt
          title="Flows"
          today="Today: archkeel view show SPEC draws a checked flow, and a tour if the spec has stops."
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

function useView(): View {
  const read = (): View => VIEWS.get(location.hash) ?? View.Overview;
  const [view, setView] = useState(read);
  useEffect(() => {
    const listener = (): void => setView(read());
    addEventListener("hashchange", listener);
    return () => removeEventListener("hashchange", listener);
  }, []);
  return view;
}

function Shell() {
  const view = useView();
  const { state, error } = useStudio();
  return (
    <>
      <aside>
        <div class="brand">
          ARCHKEEL<small>STUDIO{state ? ` · ${state.root_name}` : ""}</small>
        </div>
        <p class="label">Workspace</p>
        <nav aria-label="Workspace">
          {NAV.map((item) => (
            <NavItem key={item.view} href={`#/${item.view}`} current={item.view === view}>
              {item.name}
            </NavItem>
          ))}
        </nav>
        <p class="label">Evidence model</p>
        <Legend />
        <p class="label">Contract</p>
        <p class="contract">{state ? CONTRACT[state.contract] : "Contract: …"}</p>
      </aside>
      <main>
        {error ? <p role="alert">{error}</p> : null}
        {state ? content(view, state) : <p>Reading the Studio state…</p>}
      </main>
    </>
  );
}

const app = document.getElementById("app");
if (app) {
  startStore();
  render(<Shell />, app);
}
