/** AD-290: the Briefing: what the snapshot measured, what stands out, the stories, and a way to ask. Facts only. */
import { useEffect, useState } from "preact/hooks";
import { StoryAnswer, StoryRow, StudioState, readStories, readStory } from "../api";
import type { ChatState } from "../chat";
import { Box, Legend, Page, ProofLegend, View, viewHref } from "../components";
import { Evidence } from "../evidence";
import { Model, compact, counted, cycles, entry, fullName, hubs, seams, shortName, unknownByComponent } from "../model";
import { ContractState, ExploreState } from "../vocabulary";

const STORIES_SHOWN = 5;
const WHY: Record<ContractState, string> = {
  [ContractState.NOT_CONFIGURED]: "No contract: a policy verdict does not apply. archkeel init drafts one.",
  [ContractState.INVALID]: "archkeel.toml does not load. archkeel validate names the reason.",
  [ContractState.CONFIGURED]: "The contract loads: archkeel report shows the deviations from it.",
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
  rows.push({ text: WHY[props.state.contract], shows: [] });
  return (
    <Box title="What stands out" evidence={Evidence.Observed}>
      <p class="more">Measured from the call graph of this snapshot. No opinion.</p>
      <ul class="stands">
        {rows.slice(0, 6).map((row) => (
          <Row key={row.text} text={row.text} shows={row.shows} />
        ))}
      </ul>
    </Box>
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
  const ready = state.explore === ExploreState.DONE && model !== null;
  useEffect(() => {
    if (ready) readStories().then(setRows, () => setRows([]));
  }, [ready]);
  if (!ready) {
    return (
      <Page title="Briefing" lead={`${state.root_name}: no measured snapshot yet.`}>
        <p>
          {state.explore === ExploreState.FAILED
            ? `archkeel explore stopped with exit code ${state.exit_code}. ${state.notes.join(" ")}`
            : `Making the map: ${state.seconds} s. A large repository takes about 2 minutes.`}
        </p>
      </Page>
    );
  }
  const { totals, snapshot } = model.graph;
  const percent = totals.analyzed > 0 ? ((100 * totals.resolved) / totals.analyzed).toFixed(1) : null;
  return (
    <Page
      title="Briefing"
      lead={`${state.root_name} · ${snapshot.git_head === "" ? "no Git revision" : snapshot.git_head.slice(0, 8)}${snapshot.dirty ? " (with changes)" : ""} · digest ${snapshot.source_digest.slice(0, 8)} · explored in ${state.seconds} s · contract ${state.contract.replace("_", " ")}`}
    >
      <div class="figures">
        <Number_ value={compact(model.graph.modules.length)} label="modules" />
        <Number_ value={compact(model.graph.symbols.length)} label="functions" />
        {percent === null ? (
          <Number_ value="–" label="calls resolved" note="This snapshot has no call totals." />
        ) : (
          <Number_ value={`${percent} %`} label="calls resolved" note={`✓ ${compact(totals.resolved)} of ${compact(totals.analyzed)} · ✎ ${compact(totals.partial)} claim`} />
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
