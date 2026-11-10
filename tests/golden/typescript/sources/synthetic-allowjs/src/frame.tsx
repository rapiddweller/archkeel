import type { ReactNode } from "./plain";
export default function Frame(props: { children: ReactNode }) {
  return <div>{props.children}</div>;
}
