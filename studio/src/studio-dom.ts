type ButtonId = "zoom-in" | "zoom-out" | "story-back" | "story-next" | "story-play" |
  "inspector-toggle" | "structure-toggle" | "map" | "story" | "more" | "previous";

export function get(id: "search"): HTMLInputElement;
export function get(id: ButtonId): HTMLButtonElement;
export function get(id: string): HTMLElement;
export function get(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) throw new Error("Missing Studio element: " + id);
  return node;
}
export const canvas = get("canvas");
export const viewport = get("viewport");
export const cards = get("cards");
export const details = get("details");
export const notice = get("notice");

export function element<K extends keyof HTMLElementTagNameMap>(
  tag: K, text = "", className?: string,
): HTMLElementTagNameMap[K] {
  const result = document.createElement(tag);
  result.textContent = text;
  if (className) result.className = className;
  return result;
}
export function button(text: string, action: () => unknown, className?: string): HTMLButtonElement {
  const result = element("button", text, className);
  result.type = "button";
  result.addEventListener("click", () => Promise.resolve().then(action).catch(showError));
  return result;
}
export function showError(error: unknown, retry?: () => unknown): void {
  notice.replaceChildren(element("span", error instanceof Error ? error.message : "The request failed."));
  if (retry) notice.append(" ", button("Retry", retry));
}

export function svgElement<K extends keyof SVGElementTagNameMap>(name: K, attributes: Record<string, string | number>, parent: Element) {
  const item = document.createElementNS("http://www.w3.org/2000/svg", name);
  for (const [key, value] of Object.entries(attributes)) item.setAttribute(key, String(value));
  parent.append(item);
  return item;
}

export function breakPath(node: HTMLElement, text: string) {
  node.replaceChildren();
  for (const part of text.split(/(?<=[./])/)) node.append(part, document.createElement("wbr"));
  node.title = text;
}
