/** AD-290, AD-291: Stories: the list of the story specs and the player of one checked story. */
import { useEffect, useRef, useState } from "preact/hooks";
import { CheckStatus, CheckedStory, StepLink, StoryRow, StoryStep, readStories, readStory } from "../api";
import { Badge, Box, Page, ProofMark, View, viewHref } from "../components";
import { Evidence, Proof, proofKind } from "../evidence";
import { STORY, cardName, layoutStory } from "../story-layout";

const STEP_MS = 4000;

/** The check has five statuses and the proof three. Only `proven` is proven: never round up. */
const PROOF_OF: Record<CheckStatus, Proof> = {
  [CheckStatus.Proven]: Proof.Proven,
  [CheckStatus.Declared]: Proof.Claim,
  [CheckStatus.Claim]: Proof.Claim,
  [CheckStatus.Unknown]: Proof.Unknown,
  [CheckStatus.Missing]: Proof.Unknown,
};

const site = (file: string | null, line: number | null): string =>
  file === null ? "no place" : line === null ? file : `${file}:${line}`;

/** A partial call lists candidates and proves none: the count must show beside the claim. */
const candidatesOf = (step: StoryStep, link: StepLink): number | null =>
  (link.evidence ?? []).find((item) => item.candidates !== undefined)?.candidates ?? step.seam?.candidates ?? null;

const reduced = (): boolean => matchMedia("(prefers-reduced-motion: reduce)").matches;

function Verdict(props: { checked: CheckedStory }) {
  const verdict = props.checked.story?.verdict;
  if (verdict === undefined) return null;
  return (
    <p class="verdict" aria-label="Verdict">
      <span class="proven">{verdict.proven} ✓ proven</span> · <span class="claim">{verdict.claim} ✎ claim</span> ·{" "}
      <span class="unknown">{verdict.unknown} ? unknown</span>
      {verdict.declared > 0 ? ` · ${verdict.declared} declared` : ""}
      {verdict.missing > 0 ? ` · ${verdict.missing} missing` : ""}
      <br />
      {verdict.modules} modules · systems: {verdict.systems.length > 0 ? verdict.systems.join(", ") : "none touched"}
    </p>
  );
}

function StepPanel(props: { step: StoryStep; link: StepLink; count: number }) {
  const { step, link } = props;
  const proof = PROOF_OF[link.status];
  const touched = step.external.filter((item) => item.touched || item.direction);
  return (
    <aside class="story-panel" aria-label="Step">
      <p class="step-no">
        STEP {step.index + 1} / {props.count} <ProofMark proof={proof} />
      </p>
      <h2>{step.title ?? step.node}</h2>
      <Box title="Story" evidence={Evidence.Claim}>
        <p class="story-text">{link.note ?? "No text yet. The author adds the words."}</p>
        <p class="more">Author text is a claim. The status below comes from the check.</p>
      </Box>
      <Box title="Evidence" evidence={Evidence.Observed}>
        <p class="code">{step.node}</p>
        <p>
          <ProofMark proof={proof} /> {link.reason}
        </p>
        <ul class="pairs">
          <li>
            defined at <span class="where">{site(step.defined_at?.file ?? null, step.defined_at?.line ?? null)}</span>
          </li>
          <li>lane: {step.lane ?? "none"}</li>
          {step.seam === null ? null : (
            <li>
              seam: {step.seam.kind === "partial_call" ? "partial call" : "unresolved call"} of{" "}
              <span class="where">{step.seam.node}</span>
              {step.seam.candidates ? ` · ${step.seam.candidates} candidates` : ""}
              {step.seam.calls ? ` · ${step.seam.calls} calls` : ""}
              {step.seam.reason ? ` · ${step.seam.reason}` : ""}
            </li>
          )}
          {(link.evidence ?? []).map((item, index) => (
            <li key={index}>
              call at <span class="where">{site(item.file, item.line)}</span>
              {item.candidates === undefined ? "" : ` · ${item.candidates} candidates, none proven`}
            </li>
          ))}
        </ul>
      </Box>
      <Box title="External systems">
        {touched.length === 0 ? (
          <p class="more">No external system touched in this step.</p>
        ) : (
          <ul class="pairs">
            {touched.map((item) => (
              <li key={item.system}>
                <b>{item.system}</b>{" "}
                {item.touched ? <Badge evidence={Evidence.Observed}>touchpoint</Badge> : null}{" "}
                {item.direction ? <Badge evidence={Evidence.Claim}>{`${item.direction} · claim`}</Badge> : null}
                {(item.evidence ?? []).map((touch, index) => (
                  <span class="where" key={index}>
                    <br />
                    {touch.library} in {touch.module} · {site(touch.site.file, touch.site.line)}
                  </span>
                ))}
              </li>
            ))}
          </ul>
        )}
      </Box>
      {step.question === null ? null : (
        <Box title="Question for the architect" evidence={Evidence.Claim}>
          <p>{step.question}</p>
        </Box>
      )}
    </aside>
  );
}

function Player(props: { checked: CheckedStory }) {
  const { checked } = props;
  const story = checked.story;
  const [current, setCurrent] = useState(0);
  const [playing, setPlaying] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);
  const count = story?.steps.length ?? 0;
  const last = Math.max(0, count - 1);
  const go = (index: number): void => setCurrent(Math.max(0, Math.min(last, index)));
  const toggle = (): void => {
    if (playing) return setPlaying(false);
    if (reduced()) return go(last); // Reduced motion: show the final state, no timer.
    if (current >= last) setCurrent(0);
    setPlaying(true);
  };
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      setCurrent((index) => {
        if (index >= last) {
          setPlaying(false);
          return index;
        }
        return index + 1;
      });
    }, STEP_MS);
    return () => clearInterval(timer);
  }, [playing, last]);
  useEffect(() => {
    const listener = (event: KeyboardEvent): void => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key === "ArrowRight") go(current + 1);
      else if (event.key === "ArrowLeft") go(current - 1);
      else if (event.key === " ") {
        event.preventDefault();
        toggle();
      }
    };
    addEventListener("keydown", listener);
    return () => removeEventListener("keydown", listener);
  });
  const layout = story === null ? null : layoutStory(checked);
  // A story wider than the stage shrinks to fit: the cards keep their whole text.
  useEffect(() => {
    if (layout === null || stage.current === null) return;
    const element = stage.current;
    const fit = (): void => setScale(Math.min(1, Math.max(0.45, (element.clientWidth - 16) / layout.width)));
    fit();
    const watch = new ResizeObserver(fit);
    watch.observe(element);
    return () => watch.disconnect();
  }, [layout?.width]);
  // The camera follows the step: the stage scrolls, the reader never pans.
  useEffect(() => {
    if (layout === null || stage.current === null) return;
    const card = layout.cards[current];
    const top = card.y * scale - stage.current.clientHeight / 2 + (STORY.card.height * scale) / 2;
    const left = card.x * scale - stage.current.clientWidth / 2 + (STORY.card.width * scale) / 2;
    stage.current.scrollTo({ top: Math.max(0, top), left: Math.max(0, left), behavior: reduced() ? "auto" : "smooth" });
  }, [current, layout, scale]);
  if (story === null || layout === null || count === 0) {
    return <p class="more">This spec has no story: it has no steps to play.</p>;
  }
  const link = (index: number): StepLink => checked.steps[index];
  const proofAt = (index: number): Proof => PROOF_OF[link(index).status];
  return (
    <div class="story-player">
      <div class="story-head">
        <h1>{story.title}</h1>
        <Verdict checked={checked} />
      </div>
      {checked.snapshot_current ? null : (
        <p class="more" role="note">
          The spec names an older snapshot. The statuses are checked against the current one.
        </p>
      )}
      <div class="story-stage" ref={stage} data-reduced={reduced()}>
        <div class="story-fit" style={{ width: `${layout.width * scale}px`, height: `${layout.height * scale}px` }}>
        <div class="story-canvas" style={{ width: `${layout.width}px`, height: `${layout.height}px`, transform: `scale(${scale})` }}>
          {layout.lanes.map((lane, index) => (
            <p
              key={lane}
              class={`lane comp-${index % 10}${story.steps[current].lane === lane ? " on" : ""}`}
              style={{ left: `${index * (STORY.lane + STORY.gap)}px`, width: `${STORY.lane}px` }}
            >
              <i class="dot" aria-hidden="true" />
              {lane}
            </p>
          ))}
          {layout.chapters.map((chapter) => (
            <p key={chapter.id} class="chapter" style={{ top: `${chapter.y}px` }}>
              {chapter.title}
            </p>
          ))}
          <svg class="routes" width={layout.width} height={layout.height} aria-hidden="true">
            {layout.routes.map((route, index) =>
              route.path === null ? null : (
                <g key={index} class={`leg ${proofAt(index)}${index <= current ? " show" : ""}${index === current ? " now" : ""}`}>
                  <path d={route.path} />
                  <circle cx={route.x} cy={route.y} r={3.6} />
                </g>
              ),
            )}
          </svg>
          {story.steps.map((step, index) => {
            const proof = proofAt(index);
            const place = layout.cards[index];
            return (
              <button
                key={step.index}
                type="button"
                class={`story-card ${proof}${index <= current ? " show" : ""}${index === current ? " now" : ""}`}
                style={{ left: `${place.x}px`, top: `${place.y}px`, width: `${STORY.card.width}px`, height: `${STORY.card.height}px` }}
                title={step.node}
                aria-current={index === current ? "step" : undefined}
                onClick={() => go(index)}
              >
                <b>{cardName(step.node)}</b>
                <span class="meta">
                  <ProofMark proof={proof} /> ·{" "}
                  {candidatesOf(step, link(index)) === null
                    ? (step.defined_at?.file?.split("/").pop() ?? "no file")
                    : `${candidatesOf(step, link(index))} candidates`}
                </span>
              </button>
            );
          })}
          {layout.systems.length === 0 ? null : (
            <div class="externals" style={{ left: `${layout.externalX}px`, width: `${STORY.external}px` }}>
              <p class="head">External systems</p>
              {layout.systems.map((system) => (
                <p
                  key={system}
                  class={`system${story.steps[current].external.some((item) => item.system === system && item.touched) ? " on" : ""}`}
                >
                  {system}
                </p>
              ))}
            </div>
          )}
        </div>
        </div>
      </div>
      <StepPanel step={story.steps[current]} link={link(current)} count={count} />
      <footer class="story-controls">
        <div class="dots">
          {story.steps.map((step, index) => (
            <button
              key={step.index}
              type="button"
              class={`dotbar ${proofAt(index)}${index === current ? " now" : ""}`}
              aria-label={`Step ${index + 1}: ${proofKind(proofAt(index)).word}`}
              aria-current={index === current ? "step" : undefined}
              onClick={() => go(index)}
            />
          ))}
        </div>
        <button type="button" class="toggle" disabled={current === 0} onClick={() => go(current - 1)}>
          ← Back
        </button>
        <button type="button" class="go" onClick={toggle}>
          {playing ? "❚❚ Pause" : "▶ Play story"}
        </button>
        <button type="button" class="toggle" disabled={current === last} onClick={() => go(current + 1)}>
          Next →
        </button>
        <span class="hint">← → keys · space to play</span>
      </footer>
    </div>
  );
}

function List(props: { rows: readonly StoryRow[] }) {
  return (
    <Page title="Stories" lead="A story explains one flow of the real code. ArchKeel checks each step; the author writes the words.">
      {props.rows.length === 0 ? (
        <p class="more">
          No story yet. Ask your agent to explain a flow (skill explain-flow), or pin a path from the chat. A spec is a
          <code>.story.json</code> file in the stories folder of this root.
        </p>
      ) : (
        <div class="cards">
          {props.rows.map((row) => (
            <a key={row.id} class="map-card" href={viewHref(View.Stories, row.id)}>
              <h2>{row.title}</h2>
              <p>
                {row.id} · {row.steps} steps
              </p>
              <span class="chips">
                <span class="chip">Open the player</span>
              </span>
            </a>
          ))}
        </div>
      )}
    </Page>
  );
}

/** `id` is the story of `#/stories/<id>`, else null for the list. */
export function Stories(props: { id: string | null; ready: boolean }) {
  const { id } = props;
  const [rows, setRows] = useState<readonly StoryRow[] | null>(null);
  const [checked, setChecked] = useState<CheckedStory | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setError(null);
    setChecked(null);
    if (!props.ready) return;
    const read = id === null ? readStories().then(setRows) : readStory(id).then(setChecked);
    read.catch((failed) => setError(String(failed instanceof Error ? failed.message : failed)));
  }, [id, props.ready]);
  if (!props.ready) {
    return (
      <Page title="Stories" lead="No map yet. A story is checked against the snapshot. Overview shows the progress.">
        {null}
      </Page>
    );
  }
  if (error !== null) {
    return (
      <Page title="Stories" lead="The story cannot be shown.">
        <p role="alert">{error}</p>
        <a href={viewHref(View.Stories)}>All stories</a>
      </Page>
    );
  }
  if (id === null) return rows === null ? <p>Reading the stories…</p> : <List rows={rows} />;
  return checked === null ? <p>Checking the story…</p> : <Player checked={checked} />;
}
