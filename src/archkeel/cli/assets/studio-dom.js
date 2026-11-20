export function get(id) {
    const node = document.getElementById(id);
    if (!node)
        throw new Error("Missing Studio element: " + id);
    return node;
}
export const canvas = get("canvas");
export const viewport = get("viewport");
export const cards = get("cards");
export const details = get("details");
export const notice = get("notice");
export function element(tag, text = "", className) {
    const result = document.createElement(tag);
    result.textContent = text;
    if (className)
        result.className = className;
    return result;
}
export function button(text, action, className) {
    const result = element("button", text, className);
    result.type = "button";
    result.addEventListener("click", () => Promise.resolve().then(action).catch(showError));
    return result;
}
export function showError(error, retry) {
    notice.replaceChildren(element("span", error instanceof Error ? error.message : "The request failed."));
    if (retry)
        notice.append(" ", button("Retry", retry));
}
export function svgElement(name, attributes, parent) {
    const item = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const [key, value] of Object.entries(attributes))
        item.setAttribute(key, String(value));
    parent.append(item);
    return item;
}
export function breakPath(node, text) {
    node.replaceChildren();
    for (const part of text.split(/(?<=[./])/))
        node.append(part, document.createElement("wbr"));
    node.title = text;
    return node;
}
