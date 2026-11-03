/** AD-290: the shared components of slice 1; they take props and never call the API. */
import type { ComponentChildren } from "preact";
import { EVIDENCE, Evidence } from "./evidence";

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

export function Badge(props: { evidence: Evidence; children: ComponentChildren }) {
  return <span class={`badge ${props.evidence}`}>{props.children}</span>;
}

export function Tabs(props: { tabs: readonly { evidence: Evidence; text: string }[] }) {
  return (
    <div class="tabs">
      {props.tabs.map((tab) => (
        <span class={tab.evidence} key={tab.text}>
          {tab.text}
        </span>
      ))}
    </div>
  );
}

export function Card(props: { title: string; evidence: Evidence; children: ComponentChildren }) {
  const kind = EVIDENCE.find((item) => item.evidence === props.evidence);
  return (
    <section class="card">
      <h2>{props.title}</h2>
      {props.children}
      <Badge evidence={props.evidence}>{kind?.name}</Badge>
    </section>
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
