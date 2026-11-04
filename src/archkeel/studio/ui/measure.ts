/** AD-290: how many lines a text needs in a card. A card grows to its text; no text is cut. Pure. */

/** Width of one character of the card fonts (13 px bold and 11.5 px monospace), a little generous. */
const NAME_CHAR = 8.8;
const META_CHAR = 7.3;
const LINE = { name: 20, meta: 17 } as const;
const PAD = 16;
/** The left border and the padding of a card. */
const INSET = 28;

const linesOf = (text: string, width: number, char: number): number =>
  Math.max(1, Math.ceil((text.length * char) / Math.max(1, width - INSET)));

/** The height of a card: its name over as many lines as needed, then the facts. */
export function cardHeight(width: number, name: string, facts: readonly string[]): number {
  const metas = facts.reduce((sum, fact) => sum + linesOf(fact, width, META_CHAR), 0);
  return PAD + linesOf(name, width, NAME_CHAR) * LINE.name + metas * LINE.meta;
}
