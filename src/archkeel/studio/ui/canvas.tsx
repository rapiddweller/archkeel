/** AD-290: the Explorer island. The shell mounts the offline Explorer page in embed mode. */
import { useEffect, useRef, useState } from "preact/hooks";

/** The one message the embedded Explorer sends; it must stay equal to flow.js. */
export const ExplorerMessage = { COMPONENT_SELECTED: "component-selected" } as const;

export type SelectedComponent = { readonly id: string; readonly label: string | null };

// The canvas takes the shell tokens, so both read as one surface.
const SHARED_TOKENS: readonly (readonly [string, string])[] = [
  ["--ak-canvas", "--bg"],
  ["--ak-panel", "--panel"],
  ["--ak-card", "--raised"],
  ["--ak-line", "--line"],
  ["--ak-text", "--text"],
  ["--ak-muted", "--muted"],
];

export function ExplorerCanvas(props: {
  src: string;
  onSelect: (component: SelectedComponent | null) => void;
}) {
  const frame = useRef<HTMLIFrameElement>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const listener = (event: MessageEvent): void => {
      const data = event.data;
      // The window is the identity: a sandboxed page has the opaque origin "null".
      if (event.source !== frame.current?.contentWindow) return;
      if (data?.kind !== ExplorerMessage.COMPONENT_SELECTED) return;
      props.onSelect(typeof data.id === "string" ? { id: data.id, label: data.label ?? null } : null);
    };
    addEventListener("message", listener);
    return () => removeEventListener("message", listener);
  }, [props.onSelect]);
  const share = (): void => {
    const tokens = getComputedStyle(document.documentElement);
    const target = frame.current?.contentDocument?.documentElement.style;
    SHARED_TOKENS.forEach(([name, token]) => target?.setProperty(name, tokens.getPropertyValue(token)));
    setReady(true);
  };
  // Hidden until loaded: the page shows its report chrome until its script runs.
  return (
    <iframe
      ref={frame}
      title="Explorer"
      class={ready ? "ready" : undefined}
      src={`${props.src}?theme=dark&embed`}
      onLoad={share}
    />
  );
}
