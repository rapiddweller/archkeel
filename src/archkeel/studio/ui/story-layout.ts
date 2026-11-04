/** AD-291: the geometry of a story: one lane for each component, time runs top to bottom. Pure. */
import type { CheckedStory } from "./api";

export const STORY = {
  lane: 262,
  gap: 14,
  card: { width: 250, height: 48 },
  row: 64,
  top: 92,
  external: 200,
} as const;

export interface StoryCard {
  readonly x: number;
  readonly y: number;
  readonly lane: number;
}
export interface StoryRoute {
  /** The path from the card before to this card; null for the first step. */
  readonly path: string | null;
  readonly x: number;
  readonly y: number;
}
export interface StoryChapter {
  readonly id: string;
  readonly title: string;
  readonly y: number;
}
export interface StoryLayout {
  readonly lanes: readonly string[];
  readonly cards: readonly StoryCard[];
  readonly routes: readonly StoryRoute[];
  readonly chapters: readonly StoryChapter[];
  /** The systems that the story touches, for the fixed column at the right. */
  readonly systems: readonly string[];
  readonly width: number;
  readonly height: number;
  /** Left edge of the external column. */
  readonly externalX: number;
}

const UNLANED = "(no lane)";
const CORNER = 14;

/** The width of a character of the card font (11.5 px monospace) and the padding of a card. */
const CHAR = 7;
const PAD = 28;

/** The dotted name that fits a card: the longest end of the name; cut in the middle only when its last part is too long. */
export function cardName(name: string, width: number = STORY.card.width): string {
  const limit = Math.floor((width - PAD) / CHAR);
  const parts = name.split(".");
  let fit = "";
  for (let length = 1; length <= parts.length; length += 1) {
    const text = parts.slice(-length).join(".");
    if (text.length > limit) break;
    fit = text;
  }
  return fit === "" ? midCut(parts[parts.length - 1], limit) : fit;
}

/** A long name is cut in the middle, so that its start and its end stay visible. */
export function midCut(name: string, limit: number): string {
  if (name.length <= limit) return name;
  const keep = limit - 1;
  const head = Math.ceil(keep / 2);
  return `${name.slice(0, head)}…${name.slice(name.length - (keep - head))}`;
}

export function layoutStory(checked: CheckedStory): StoryLayout {
  const steps = checked.story?.steps ?? [];
  const lanes: string[] = [];
  const laneOf = steps.map((step) => {
    const name = step.lane ?? UNLANED;
    if (!lanes.includes(name)) lanes.push(name);
    return lanes.indexOf(name);
  });
  const systems = [...new Set(steps.flatMap((step) => step.external.filter((item) => item.touched).map((item) => item.system)))];
  const centre = (lane: number): number => lane * (STORY.lane + STORY.gap) + STORY.lane / 2;
  const cards = steps.map((_, index) => ({
    x: centre(laneOf[index]) - STORY.card.width / 2,
    y: STORY.top + index * STORY.row,
    lane: laneOf[index],
  }));
  const routes = cards.map((card, index): StoryRoute => {
    if (index === 0) return { path: null, x: card.x + STORY.card.width / 2, y: card.y };
    const before = cards[index - 1];
    const startX = before.x + STORY.card.width / 2;
    const startY = before.y + STORY.card.height;
    if (before.lane === card.lane) return { path: `M${startX} ${startY} V${card.y}`, x: startX, y: card.y };
    const direction = card.lane > before.lane ? 1 : -1;
    const midY = card.y + STORY.card.height / 2;
    const endX = direction > 0 ? card.x : card.x + STORY.card.width;
    const path = `M${startX} ${startY} V${midY - CORNER} Q${startX} ${midY} ${startX + direction * CORNER} ${midY} H${endX}`;
    return { path, x: endX, y: midY };
  });
  const chapters: StoryChapter[] = [];
  const titles = new Map((checked.story?.chapters ?? []).map((chapter) => [chapter.id, chapter.title]));
  steps.forEach((step, index) => {
    if (step.chapter !== null && chapters.at(-1)?.id !== step.chapter) {
      chapters.push({ id: step.chapter, title: titles.get(step.chapter) ?? step.chapter, y: cards[index].y - 17 });
    }
  });
  const lanesWidth = Math.max(1, lanes.length) * (STORY.lane + STORY.gap) - STORY.gap;
  return {
    lanes,
    cards,
    routes,
    chapters,
    systems,
    width: lanesWidth + (systems.length > 0 ? STORY.external + 24 : 0),
    height: STORY.top + steps.length * STORY.row + 24,
    externalX: lanesWidth + 24,
  };
}
