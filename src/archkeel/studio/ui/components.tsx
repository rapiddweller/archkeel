/** AD-290: the shared components of slice 1; they take props and never call the API. */
import type { ComponentChildren } from "preact";
import { EVIDENCE, Evidence, PROOF, Proof, proofKind } from "./evidence";

/** The pages of the shell; the URL hash is `#/<view>`, and Component takes `#/component/<n>[/<package>]`, Module `#/module/<n>`, Explore `#/explore/<function>` and Stories `#/stories/<id>`. */
export const View = {
  Overview: "overview",
  Map: "map",
  Component: "component",
  Module: "module",
  Explore: "explore",
  Report: "report",
  Stories: "stories",
  Impact: "impact",
  Target: "target",
} as const;
export type View = (typeof View)[keyof typeof View];

/** `id` is the function, component, module or story; `pkg` is a package path inside a component. */
export const viewHref = (view: View, id?: number | string, pkg?: string): string =>
  id === undefined ? `#/${view}` : pkg === undefined ? `#/${view}/${id}` : `#/${view}/${id}/${pkg}`;

export function NavItem(props: { href: string; current: boolean; children: ComponentChildren }) {
  return (
    <a href={props.href} aria-current={props.current ? "page" : undefined}>
      {props.children}
    </a>
  );
}

export function Legend() {
  return (
    <ul class="legend">
      {EVIDENCE.map((kind) => (
        <li class={kind.evidence} key={kind.evidence}>
          {kind.name} = {kind.meaning}
        </li>
      ))}
    </ul>
  );
}

/** The legend of the call proof: one line for each status, glyph and word. */
export function ProofLegend() {
  return (
    <ul class="legend">
      {PROOF.map((kind) => (
        <li class={kind.proof} key={kind.proof}>
          <span aria-hidden="true">{kind.glyph}</span> {kind.word} = {kind.meaning}
        </li>
      ))}
    </ul>
  );
}

/** Glyph and word of a call proof; the colour only repeats them. */
export function ProofMark(props: { proof: Proof }) {
  const kind = proofKind(props.proof);
  return (
    <span class={`mark ${props.proof}`}>
      <span aria-hidden="true">{kind.glyph}</span> {kind.word}
    </span>
  );
}

export function Badge(props: { evidence: Evidence; children: ComponentChildren }) {
  return <span class={`badge ${props.evidence}`}>{props.children}</span>;
}

export function Panel(props: { title: string; children: ComponentChildren }) {
  return (
    <aside class="panel" aria-label={props.title}>
      <p class="label">{props.title}</p>
      {props.children}
    </aside>
  );
}

export function Page(props: { title: string; lead: string; children: ComponentChildren }) {
  return (
    <>
      <h1>{props.title}</h1>
      <p class="lead">{props.lead}</p>
      {props.children}
    </>
  );
}

/** A titled box of a side panel; the badge says what kind of evidence the box shows. */
export function Box(props: { title: string; evidence?: Evidence; children: ComponentChildren }) {
  const kind = EVIDENCE.find((item) => item.evidence === props.evidence);
  return (
    <section class="box">
      <h3>
        {props.title}
        {kind ? <Badge evidence={kind.evidence}>{kind.name}</Badge> : null}
      </h3>
      {props.children}
    </section>
  );
}
