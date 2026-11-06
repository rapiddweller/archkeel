/** AD-290: the Briefing: what the snapshot measured, what stands out, the stories, and a way to ask. Facts only. */
import { useEffect, useState } from "preact/hooks";
import { StoryAnswer, StoryRow, StudioState, readStories, readStory } from "../api";
import type { ChatState } from "../chat";
import { Badge, Box, DiagnosticNotes, ExploreFailure, Legend, Page, ProofLegend, View, viewHref } from "../components";
import { Evidence } from "../evidence";
import { Model, compact, counted, cycles, entry, fullName, hubs, seams, shortName, unknownByComponent } from "../model";
import { ComponentSource, ContractState, ExploreState } from "../vocabulary";

const STORIES_SHOWN = 5;
const COMPONENTS_SHOWN = 6;
const WHY: Record<ContractState, string> = {
  [ContractState.NOT_CONFIGURED]: "No contract · no policy verdict. archkeel init drafts one.",
  [ContractState.INVALID]: "archkeel.toml does not load. archkeel validate names the reason.",
  [ContractState.CONFIGURED]: "The contract loads: archkeel report shows the deviations from it.",
};
const CONTRACT_STATUS: Record<ContractState, string> = {
  [ContractState.NOT_CONFIGURED]: "No contract · no policy verdict",
  [ContractState.INVALID]: "Contract invalid",
  [ContractState.CONFIGURED]: "Contract configured",
};

function Number_(props: { value: string; label: string; note?: string }) {
  return (
    <section class="figure">
      <b>{props.value}</b>
      <span>{props.label}</span>
      {props.note ? <small>{props.note}</small> : null}
    </section>
  );
}

function SnapshotStatus(props: { state: StudioState; withGraph: boolean }) {
  const { state } = props;
  if (state.explore === ExploreState.INCOMPLETE) {
    return (
      <section class="brief-status incomplete" role="status">
        <strong>Snapshot is incomplete</strong>
        {props.withGraph ? null : <span>No graph is available.</span>}
        <span>{props.withGraph ? "Next: inspect notes." : "Next: inspect diagnostic details."}</span>
        <DiagnosticNotes notes={state.notes} />
      </section>
    );
  }
  if (state.explore === ExploreState.FAILED) {
    return <ExploreFailure exitCode={state.exit_code} notes={state.notes} />;
  }
  return state.explore === ExploreState.IDLE || state.explore === ExploreState.RUNNING ? (
    <section class="brief-status running" role="status">
      <strong>{state.explore === ExploreState.IDLE ? "Explore is starting" : `Explore is running · ${state.seconds} s`}</strong>
      <span>Next: wait for the snapshot; this page updates when it is ready.</span>
    </section>
  ) : (
    <section class="brief-status failed" role="alert">
      <strong>Explore finished, but no graph is available</strong>
      <span>Next: restart Studio to run Explore again.</span>
    </section>
  );
}

/** One measured sentence and where it opens. */
function Row(props: { text: string; shows: readonly { label: string; href: string }[] }) {
  return (
    <li class="stand">
      <span>{props.text}</span>
      {props.shows.map((show) => (
        <a key={show.href + show.label} class="toggle" href={show.href}>
          Show {show.label}
        </a>
      ))}
    </li>
  );
}

function Standing(props: { model: Model; state: StudioState }) {
  const { model } = props;
  const rows: { text: string; shows: { label: string; href: string }[] }[] = [];
  const top = hubs(model, 3);
  if (top.length > 0) {
    rows.push({
      text: `Most called: ${top.map((symbol) => `${shortName(model, symbol)} (${counted(model.incoming[symbol].length, "caller")})`).join(", ")}.`,
      shows: top.map((symbol) => ({ label: shortName(model, symbol), href: viewHref(View.Explore, symbol) })),
    });
  }
  for (const group of cycles(model)) {
    rows.push({
      text: `Components call each other in a cycle: ${group.map((component) => model.graph.components[component][0]).join(", ")}.`,
      shows: group.slice(0, 3).map((component) => ({ label: model.graph.components[component][0], href: viewHref(View.Component, component) })),
    });
  }
  const gaps = seams(model, 3);
  if (gaps.length > 0) {
    rows.push({
      text: `Largest gaps in the call graph: ${gaps.map((symbol) => `${shortName(model, symbol)} (${model.graph.symbols[symbol][5]} unknown calls, ${counted(model.outgoing[symbol].length, "known callee")})`).join(", ")}.`,
      shows: gaps.map((symbol) => ({ label: shortName(model, symbol), href: viewHref(View.Explore, symbol) })),
    });
  }
  const unknown = unknownByComponent(model, 3);
  if (unknown.length > 0) {
    rows.push({
      text: `Most unknown calls: ${unknown.map((entryRow) => `${model.graph.components[entryRow.component][0]} (${entryRow.unknown})`).join(", ")}.`,
      shows: unknown.map((entryRow) => ({ label: model.graph.components[entryRow.component][0], href: viewHref(View.Component, entryRow.component) })),
    });
  }
  return (
    <>
      <details class="briefing-signals">
        <summary>What stands out · {Math.min(rows.length, 6)} measured facts</summary>
        {rows.length > 0 ? (
          <Box title="What stands out" evidence={Evidence.Observed}>
            <ul class="stands">
              {rows.slice(0, 6).map((row) => (
                <Row key={row.text} text={row.text} shows={row.shows} />
              ))}
            </ul>
          </Box>
        ) : null}
      </details>
      <p class="more">{WHY[props.state.contract]}</p>
    </>
  );
}

function Components(props: { model: Model }) {
  const { model } = props;
  const components = model.graph.components
    .map(([name], component) => ({ name, component, stats: model.stats[component] }))
    .sort((a, b) => b.stats.modules - a.stats.modules || b.stats.symbols - a.stats.symbols || a.name.localeCompare(b.name))
    .slice(0, COMPONENTS_SHOWN);
  const declared = model.graph.components_from === ComponentSource.CONTRACT;
  return (
    <section aria-labelledby="components-heading">
      <div class="briefing-section-title">
        <h2 id="components-heading">Components</h2>
        <span class="briefing-component-count">{components.length} of {model.graph.components.length} · <a href={viewHref(View.Map)}>See all in Architecture</a></span>
        <Badge evidence={declared ? Evidence.Target : Evidence.Observed}>
          {declared ? "Declared groups: contract" : "Base groups: observed package layout"}
        </Badge>
      </div>
      {components.length === 0 ? (
        <p class="more">No components found in this snapshot.</p>
      ) : (
        <div class="cards component-cards">
          {components.map(({ name, component, stats }) => (
            <a key={component} class="card component-card" href={viewHref(View.Component, component)}>
              <h3>{name}</h3>
              <Badge evidence={Evidence.Observed}>Measured</Badge>
              <span>{counted(stats.modules, "module")} · {counted(stats.symbols, "symbol")}</span>
              <span>{counted(stats.withUnknown, "symbol")} with unknown calls</span>
            </a>
          ))}
        </div>
      )}
    </section>
  );
}

const day = (made: string | null): string => (made === null ? "" : ` · created ${made.slice(0, 10)}`);

function Stories(props: { model: Model; rows: readonly StoryRow[] | null }) {
  const [answers, setAnswers] = useState<Readonly<Record<string, StoryAnswer>>>({});
  const shown = [...(props.rows ?? [])]
    .sort((a, b) => (b.created ?? "").localeCompare(a.created ?? "") || a.id.localeCompare(b.id))
    .slice(0, STORIES_SHOWN);
  useEffect(() => {
    shown.forEach((row) => {
      readStory(row.id).then(
        (answer) => setAnswers((known) => ({ ...known, [row.id]: answer })),
        () => undefined,
      );
    });
  }, [props.rows]);
  const start = entry(props.model);
  return (
    <Box title="Stories">
      {start === null ? null : (
        <p>
          <a class="toggle" href={viewHref(View.Explore, start)}>
            How does it start?
          </a>{" "}
          <span class="more">Heuristic: {fullName(props.model, start)} is called by nobody and calls most.</span>
        </p>
      )}
      {props.rows === null ? (
        <p class="more">Reading the stories…</p>
      ) : shown.length === 0 ? (
        <p class="more">No story yet. Ask your agent: use explain-flow.</p>
      ) : (
        <ul class="stands">
          {shown.map((row) => {
            const verdict = answers[row.id]?.checked.story?.verdict;
            return (
              <li key={row.id} class="stand">
                <a href={viewHref(View.Stories, row.id)}>{row.title}</a>
                <span class="more">
                  {counted(row.steps, "step")}
                  {verdict === undefined ? "" : ` · ✓ ${verdict.proven} · ✎ ${verdict.claim} · ? ${verdict.unknown + verdict.missing}`} · {row.source}
                  {day(row.created)}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </Box>
  );
}

function Ask(props: { chat: ChatState }) {
  const [text, setText] = useState("");
  return (
    <Box title="Ask">
      <form
        class="ask"
        onSubmit={(event) => {
          event.preventDefault();
          const question = text.trim();
          if (question === "") return;
          // The question opens the chat panel of the Architecture page.
          props.chat.show(true);
          props.chat.ask(question, null);
          location.hash = viewHref(View.Map);
        }}
      >
        <input type="text" value={text} maxLength={2000} placeholder="Ask about this code" aria-label="Question" onInput={(event) => setText(event.currentTarget.value)} />
        <button type="submit" class="go" disabled={text.trim() === ""}>
          Ask
        </button>
      </form>
    </Box>
  );
}

export function Briefing(props: { state: StudioState; model: Model | null; chat: ChatState }) {
  const { state, model } = props;
  const [rows, setRows] = useState<readonly StoryRow[] | null>(null);
  const ready =
    (state.explore === ExploreState.DONE || state.explore === ExploreState.INCOMPLETE) && model !== null;
  useEffect(() => {
    if (ready) readStories().then(setRows, () => setRows([]));
  }, [ready]);
  if (!ready) {
    return (
      <Page title="Briefing" lead={`${state.root_name}: no measured snapshot yet.`}>
        <SnapshotStatus state={state} withGraph={false} />
      </Page>
    );
  }
  const { totals, snapshot } = model.graph;
  const percent = totals.analyzed > 0 ? ((100 * totals.resolved) / totals.analyzed).toFixed(1) : null;
  return (
    <Page
      title="Briefing"
      lead={`${state.root_name} · ${snapshot.git_head === "" ? "no Git revision" : snapshot.git_head.slice(0, 8)}${snapshot.dirty ? " (with changes)" : ""} · ${CONTRACT_STATUS[state.contract]}`}
    >
      {state.explore === ExploreState.INCOMPLETE ? (
        <SnapshotStatus state={state} withGraph />
      ) : null}
      <Components model={model} />
      <div class="figures">
        <Number_ value={compact(model.graph.modules.length)} label="modules" />
        <Number_ value={compact(model.graph.symbols.length)} label="symbols" />
        {percent === null ? (
          <Number_ value="–" label="calls resolved" note="This snapshot has no call totals." />
        ) : (
          <Number_ value={`${percent} %`} label="calls resolved" note={`✓ ${compact(totals.resolved)} of ${compact(totals.analyzed)} · ✎ ${compact(totals.partial)} partial`} />
        )}
        <Number_ value={compact(totals.unresolved)} label="unknown calls" note="? no target found" />
      </div>
      <Standing model={model} state={state} />
      <Stories model={model} rows={rows} />
      <Ask chat={props.chat} />
      <Box title="Marks">
        <Legend />
        <ProofLegend />
      </Box>
    </Page>
  );
}
