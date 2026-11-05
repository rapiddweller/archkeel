/** AD-290, AD-292: the chat panel. Agent text is a claim; only Studio makes an OBSERVED fact. */
import { useState } from "preact/hooks";
import { ChatFailed, SnapshotCompleteness, askChat, readDraft } from "./api";
import type { ChatAnswer, ChatBlock, ChatMode, Fact } from "./api";
import { Badge, View, viewHref } from "./components";
import { Evidence } from "./evidence";
import { Model, findSymbol, fullName, shortName, tailPath } from "./model";
import { ChatBlockKind, ChatError } from "./vocabulary";
import type { AgentKind } from "./vocabulary";

/** What the conversation holds, in order. */
const TurnKind = { Ask: "ask", Answer: "answer", Failed: "failed" } as const;
type TurnKind = (typeof TurnKind)[keyof typeof TurnKind];
type Turn =
  | { readonly kind: typeof TurnKind.Ask; readonly text: string }
  | { readonly kind: typeof TurnKind.Answer; readonly answer: ChatAnswer }
  | { readonly kind: typeof TurnKind.Failed; readonly text: string };

export interface ChatState {
  readonly turns: readonly Turn[];
  readonly busy: boolean;
  readonly agent: AgentKind;
  readonly snapshotCompleteness: SnapshotCompleteness;
  /** The chat panel is open: the page that asks (the Briefing) opens it for the pages after it. */
  readonly shown: boolean;
  readonly show: (open: boolean) => void;
  readonly ask: (question: string, context: string | null, mode?: ChatMode) => void;
}

const REASON: Record<ChatError, string> = {
  [ChatError.INVALID_REQUEST]: "The question or the selected function was not accepted.",
  [ChatError.UNSUPPORTED_MEDIA_TYPE]: "The request was not JSON.",
  [ChatError.LENGTH_REQUIRED]: "The request had no length.",
  [ChatError.BODY_TOO_LARGE]: "The question is too long.",
  [ChatError.SNAPSHOT_NOT_READY]: "This snapshot is not available for chat.",
  [ChatError.BUSY]: "The agent still answers the last question. Ask again when it is done.",
  [ChatError.AGENT_NOT_INSTALLED]: "No agent found. Install claude or codex and start Studio again.",
  [ChatError.AGENT_FAILED]: "The agent failed.",
  [ChatError.AGENT_TIMEOUT]: "The agent took too long and was stopped.",
  [ChatError.OUTPUT_TOO_LARGE]: "The agent answer was too large and was discarded.",
  [ChatError.REPOSITORY_CHANGED]: "The agent changed a file. Studio discarded the answer.",
  [ChatError.INVALID_ANSWER]: "The agent answer had the wrong shape and was discarded.",
};

function failure(error: unknown): string {
  if (error instanceof ChatFailed) {
    const reason = error.code === null ? null : REASON[error.code];
    if (
      error.code === ChatError.SNAPSHOT_NOT_READY ||
      error.code === ChatError.AGENT_NOT_INSTALLED ||
      error.code === ChatError.AGENT_FAILED
    ) {
      return `${reason} ${error.message}`;
    }
    // Without a code the route is missing or refused: an older Studio, or a wrong origin.
    return reason ?? `The chat is not available (${error.status}): ${error.message}`;
  }
  return String(error);
}

/** The one conversation; the shell keeps it, so it survives a change of page. */
export function useChat(
  agent: AgentKind,
  snapshotCompleteness: SnapshotCompleteness,
): ChatState {
  const [turns, setTurns] = useState<readonly Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [shown, show] = useState(false);
  const ask = (question: string, context: string | null, mode: ChatMode = "answer"): void => {
    if (busy) return;
    setTurns((before) => [...before, { kind: TurnKind.Ask, text: question }]);
    setBusy(true);
    askChat(question, context, mode).then(
      (answer) => setTurns((before) => [...before, { kind: TurnKind.Answer, answer }]),
      (error) => setTurns((before) => [...before, { kind: TurnKind.Failed, text: failure(error) }]),
    ).finally(() => setBusy(false));
  };
  return { turns, busy, agent, snapshotCompleteness, shown, show, ask };
}

const QUICK: readonly string[] = [
  "What does this function do?",
  "Who calls it, and why?",
  "What does it call?",
  "Where is the call graph unsure around it?",
];

function Refs(props: { model: Model; refs: readonly string[] }) {
  return (
    <>
      {props.refs.map((name) => {
        const symbol = findSymbol(props.model, name);
        return symbol === null ? null : (
          <a key={name} class="ref" href={viewHref(View.Explore, symbol)} title={name}>
            {shortName(props.model, symbol)}
          </a>
        );
      })}
    </>
  );
}

function Observed(props: {
  model: Model;
  facts: readonly Fact[];
  completeness: SnapshotCompleteness;
}) {
  const note = props.completeness === SnapshotCompleteness.INCOMPLETE
    ? "incomplete snapshot; zero cannot establish absence"
    : "snapshot-local counts; zero does not prove absence";
  return (
    <section class="blk obs" aria-label="Observed">
      <h5>
        <span aria-hidden="true">✓</span> OBSERVED <small>{note}</small>
      </h5>
      <ul class="pairs">
        {props.facts.map((fact) => {
          const symbol = findSymbol(props.model, fact.qualified_name);
          return (
            <li key={fact.qualified_name}>
              {symbol === null ? (
                <b>{fact.qualified_name}</b>
              ) : (
                <a href={viewHref(View.Explore, symbol)} title={fact.qualified_name}>
                  {shortName(props.model, symbol)}
                </a>
              )}{" "}
              <span class="where">{fact.file ? `${tailPath(fact.file)}:${fact.line}` : "no place"}</span>
              <br />
              {fact.resolved_callers} callers · {fact.resolved_callees} callees · {fact.unknown_calls} unknown
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Proposal(props: { model: Model; block: ChatBlock; context: string | null; ask: ChatState["ask"] }) {
  const { block } = props;
  const from = block.refs[0] ?? props.context;
  const [draft, setDraft] = useState<string | null>(null);
  const pin = (): void => {
    if (from === null) return;
    readDraft(from).then(
      (spec) => setDraft(JSON.stringify(spec, null, 2)),
      (error) => setDraft(String(error)),
    );
  };
  return (
    <section class="blk prop" aria-label="Proposed">
      <h5>
        <span aria-hidden="true">◌</span> {block.label}
      </h5>
      <p class="text">{block.text}</p>
      <p class="refs">
        <Refs model={props.model} refs={block.refs} />
      </p>
      <p class="actions">
        <button
          type="button"
          class="toggle"
          disabled={from === null}
          onClick={() => props.ask(
            `Draft a story that starts at ${from} and follows the listed calls.`,
            from,
            "story",
          )}
        >
          Draft a story
        </button>
        <button type="button" class="toggle" disabled={from === null} onClick={pin}>
          Pin to story
        </button>
      </p>
      {draft === null ? null : (
        <>
          <p class="more">
            Draft spec along the traced path, with no text. Studio writes nothing: save it as a
            <code>.story.json</code> file in the stories folder, or give it to your agent.
          </p>
          <pre class="code draft">{draft}</pre>
        </>
      )}
    </section>
  );
}

function Claim(props: { model: Model; block: ChatBlock }) {
  return (
    <section class="blk cl" aria-label="Claim">
      <h5>
        <span aria-hidden="true">✎</span> CLAIM <small>agent text; refs only anchor listed names</small>
      </h5>
      <p class="text">{props.block.text}</p>
      <p class="refs">
        <Refs model={props.model} refs={props.block.refs} />
      </p>
    </section>
  );
}

function Answer(props: { model: Model; answer: ChatAnswer; context: string | null; ask: ChatState["ask"] }) {
  const { answer, model } = props;
  if (answer.story) {
    return (
      <StoryDraftView draft={answer.story} exploreCompleteness={answer.snapshot_completeness} />
    );
  }
  return (
    <div class="msg agent">
      <p class="more" role="status">
        Agent: {answer.agent} · snapshot: {answer.snapshot_completeness}. Refs show names listed in this snapshot;
        they do not verify the claim. {answer.snapshot_completeness === SnapshotCompleteness.INCOMPLETE
          ? "Missing refs or calls do not establish absence."
          : "A missing ref does not establish absence from the code."}
      </p>
      {answer.blocks.map((block, index) =>
        block.kind === ChatBlockKind.PROPOSAL ? (
          <Proposal key={index} model={model} block={block} context={props.context} ask={props.ask} />
        ) : (
          <Claim key={index} model={model} block={block} />
        ),
      )}
      {answer.facts.length > 0 ? (
        <Observed model={model} facts={answer.facts} completeness={answer.snapshot_completeness} />
      ) : null}
      {answer.dropped_refs.length > 0 ? (
        <p class="more">
          {answer.dropped_refs.length} reference{answer.dropped_refs.length === 1 ? "" : "s"} not found by exact name
          in this snapshot; this does not establish absence from the code.
        </p>
      ) : null}
    </div>
  );
}

function StoryDraftView(props: {
  draft: NonNullable<ChatAnswer["story"]>;
  exploreCompleteness: SnapshotCompleteness;
}) {
  const download = (): void => {
    const id = props.draft.candidate.story.id;
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(props.draft.candidate, null, 2)], { type: "application/json" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${id}.story.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const checked = props.draft.checked;
  const verdict = checked.story?.verdict;
  return (
    <section class="blk story-draft" aria-label="Checked story draft">
      <h5>{checked.title} · checked draft</h5>
      <p class="more" role="status">
        Explore: {props.exploreCompleteness}; source coverage: {checked.snapshot_completeness}. {props.exploreCompleteness === SnapshotCompleteness.INCOMPLETE || checked.snapshot_completeness === SnapshotCompleteness.INCOMPLETE
          ? "At least one completeness check is incomplete; UNKNOWN does not establish absence."
          : "Statuses come from the current snapshot."}
      </p>
      {verdict === undefined ? null : (
        <p class="more">
          {verdict.proven} proven · {verdict.claim} claim · {verdict.unknown} unknown · {verdict.missing} missing
        </p>
      )}
      <ol>
        {checked.steps.map((step, index) => (
          <li key={index}>
            {step.source === null ? "Start" : step.source} → {step.target}: <b>{step.status}</b>
            {step.reason ? ` · ${step.reason}` : ""}
            {step.note ? ` · ${step.note}` : ""}
          </li>
        ))}
      </ol>
      <details>
        <summary>View candidate JSON</summary>
        <pre class="code draft">{JSON.stringify(props.draft.candidate, null, 2)}</pre>
      </details>
      <p class="actions">
        <button type="button" class="toggle" onClick={download}>Download checked story JSON</button>
      </p>
      <p class="more">The downloaded candidate is unchanged. Studio did not save it in the project.</p>
    </section>
  );
}

export function ChatPanel(props: { model: Model; symbol: number | null; chat: ChatState }) {
  const { model, symbol, chat } = props;
  const [text, setText] = useState("");
  const context = symbol === null ? null : fullName(model, symbol);
  const last = [...chat.turns].reverse().find((turn) => turn.kind === TurnKind.Answer);
  const send = (question: string): void => {
    const trimmed = question.trim();
    if (trimmed === "" || chat.busy) return;
    chat.ask(trimmed, context);
    setText("");
  };
  return (
    <section class="chat" aria-label="Ask the agent">
      <header>
        <p class="label">
          Ask the agent <Badge evidence={Evidence.Claim}>Claim</Badge>
        </p>
        <p class="agent-name">Selected agent: {chat.agent}</p>
        <p class="more">Snapshot: {chat.snapshotCompleteness}</p>
        <p class="chip context" title={context ?? undefined}>
          {symbol === null ? "No function selected" : `Context: ${shortName(model, symbol)}`}
        </p>
      </header>
      <div class="thread" role="log" aria-live="polite">
        {chat.turns.length === 0 ? (
          <p class="more">
            The agent reads the code and answers. What it says is a claim. Studio adds what it measured: those
            lines read OBSERVED.
          </p>
        ) : null}
        {chat.turns.map((turn, index) => {
          switch (turn.kind) {
            case TurnKind.Ask:
              return (
                <p key={index} class="msg user">
                  {turn.text}
                </p>
              );
            case TurnKind.Answer:
              return <Answer key={index} model={model} answer={turn.answer} context={context} ask={chat.ask} />;
            case TurnKind.Failed:
              return (
                <p key={index} class="msg failed" role="alert">
                  {turn.text}
                </p>
              );
          }
        })}
        {chat.busy ? <p class="msg busy">The agent reads the code…</p> : null}
      </div>
      <p class="quick">
        {QUICK.map((question) => (
          <button key={question} type="button" class="toggle" disabled={chat.busy} onClick={() => send(question)}>
            {question}
          </button>
        ))}
      </p>
      <form
        class="ask"
        onSubmit={(event) => {
          event.preventDefault();
          send(text);
        }}
      >
        <input
          type="text"
          value={text}
          maxLength={2000}
          placeholder="Ask about this function"
          aria-label="Question"
          onInput={(event) => setText(event.currentTarget.value)}
        />
        <button type="submit" class="go" disabled={chat.busy || text.trim() === ""}>
          Ask
        </button>
        <button
          type="button"
          class="toggle"
          disabled={chat.busy || context === null}
          onClick={() => {
            chat.ask(text.trim() || "Draft a story for this flow.", context, "story");
            setText("");
          }}
        >
          Draft story
        </button>
      </form>
    </section>
  );
}
