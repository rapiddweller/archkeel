/** AD-290, AD-292: the chat panel. Agent text is a claim; only Studio makes an OBSERVED fact. */
import { useState } from "preact/hooks";
import { ChatAnswer, ChatBlock, ChatFailed, Fact, askChat, readDraft } from "./api";
import { Badge, View, viewHref } from "./components";
import { Evidence } from "./evidence";
import { Model, findSymbol, fullName, shortName, tailPath } from "./model";
import { ChatBlockKind, ChatError } from "./vocabulary";

/** What the conversation holds, in order. */
export const TurnKind = { Ask: "ask", Answer: "answer", Failed: "failed" } as const;
export type TurnKind = (typeof TurnKind)[keyof typeof TurnKind];
export type Turn =
  | { readonly kind: typeof TurnKind.Ask; readonly text: string }
  | { readonly kind: typeof TurnKind.Answer; readonly answer: ChatAnswer }
  | { readonly kind: typeof TurnKind.Failed; readonly text: string };

export interface ChatState {
  readonly turns: readonly Turn[];
  readonly busy: boolean;
  readonly ask: (question: string, context: string | null) => void;
}

const REASON: Record<ChatError, string> = {
  [ChatError.INVALID_REQUEST]: "The question or the selected function was not accepted.",
  [ChatError.UNSUPPORTED_MEDIA_TYPE]: "The request was not JSON.",
  [ChatError.LENGTH_REQUIRED]: "The request had no length.",
  [ChatError.BODY_TOO_LARGE]: "The question is too long.",
  [ChatError.SNAPSHOT_NOT_READY]: "The map is not ready yet. Wait for Explore to finish.",
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
    // Without a code the route is missing or refused: an older Studio, or a wrong origin.
    return reason ?? `The chat is not available (${error.status}): ${error.message}`;
  }
  return String(error);
}

/** The one conversation; the shell keeps it, so it survives a change of page. */
export function useChat(): ChatState {
  const [turns, setTurns] = useState<readonly Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const ask = (question: string, context: string | null): void => {
    if (busy) return;
    setTurns((before) => [...before, { kind: TurnKind.Ask, text: question }]);
    setBusy(true);
    askChat(question, context).then(
      (answer) => setTurns((before) => [...before, { kind: TurnKind.Answer, answer }]),
      (error) => setTurns((before) => [...before, { kind: TurnKind.Failed, text: failure(error) }]),
    ).finally(() => setBusy(false));
  };
  return { turns, busy, ask };
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

function Observed(props: { model: Model; facts: readonly Fact[] }) {
  return (
    <section class="blk obs" aria-label="Observed">
      <h5>
        <span aria-hidden="true">✓</span> OBSERVED <small>measured by Studio</small>
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
          onClick={() => props.ask(`Draft a story that starts at ${from} and follows the resolved calls.`, props.context)}
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
        <span aria-hidden="true">✎</span> CLAIM <small>agent text, not proof</small>
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
  return (
    <div class="msg agent">
      {answer.blocks.map((block, index) =>
        block.kind === ChatBlockKind.PROPOSAL ? (
          <Proposal key={index} model={model} block={block} context={props.context} ask={props.ask} />
        ) : (
          <Claim key={index} model={model} block={block} />
        ),
      )}
      {answer.facts.length > 0 ? <Observed model={model} facts={answer.facts} /> : null}
      {answer.dropped_refs.length > 0 ? (
        <p class="more">
          {answer.dropped_refs.length} reference{answer.dropped_refs.length === 1 ? "" : "s"} of the agent dropped:
          not in the snapshot.
        </p>
      ) : null}
    </div>
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
        <p class="agent-name">Agent: {last?.kind === TurnKind.Answer ? last.answer.agent : "not asked yet"}</p>
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
      </form>
    </section>
  );
}
