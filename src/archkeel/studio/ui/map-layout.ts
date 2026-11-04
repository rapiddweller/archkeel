/** AD-290: the layout of the component Map: role bands by net call flow, and the lines. */
import type { Model } from "./model";

export const MAP_CARD = { width: 250, height: 172, gapX: 210, gapY: 30, left: 40, top: 70 } as const;

const STRONG_SHARE = 0.06;
const LABEL_SHARE = 0.12;
const MOSTLY_PARTIAL = 0.5;

export interface MapLine {
  readonly from: number;
  readonly to: number;
  readonly calls: number;
  readonly partial: number;
  readonly path: string;
  readonly width: number;
  /** Only strong lines are drawn at full weight. */
  readonly strong: boolean;
  /** Only strong lines carry their count. */
  readonly labeled: boolean;
  /** At least half of the calls are partial: the line is a claim. */
  readonly mostlyPartial: boolean;
  readonly middle: readonly [number, number];
}

export interface MapLayout {
  readonly bandNames: readonly string[];
  readonly band: readonly number[];
  readonly positions: readonly (readonly [number, number])[];
  readonly width: number;
  readonly height: number;
  readonly lines: readonly MapLine[];
}

const BAND_NAMES: Record<number, readonly string[]> = {
  1: ["All components"],
  2: ["Callers", "Foundations"],
  3: ["Callers", "Middle", "Foundations"],
};

/** Components that mostly call go left; components that are mostly called go right. */
function bandsOf(model: Model): number[] {
  const count = model.graph.components.length;
  const score = model.stats.map((stat, index) => {
    const total = stat.callsOut + stat.callsIn;
    return { index, net: (stat.callsOut - stat.callsIn) / Math.max(1, total), total };
  });
  score.sort((a, b) => b.net - a.net || b.total - a.total);
  const bands = count <= 6 ? 2 : 3;
  const per = Math.ceil(count / bands);
  const band = new Array<number>(count).fill(0);
  score.forEach(({ index }, rank) => (band[index] = Math.min(bands - 1, Math.floor(rank / per))));
  return band;
}

function curve(
  from: readonly [number, number],
  to: readonly [number, number],
  fromBand: number,
  toBand: number,
): { path: string; middle: readonly [number, number] } {
  const { width, height } = MAP_CARD;
  const y1 = from[1] + height / 2;
  const y2 = to[1] + height / 2;
  if (toBand > fromBand) {
    const x1 = from[0] + width;
    const mid = (x1 + to[0]) / 2;
    return { path: `M${x1} ${y1} C${mid} ${y1} ${mid} ${y2} ${to[0]} ${y2}`, middle: [mid, (y1 + y2) / 2] };
  }
  if (toBand < fromBand) {
    const x2 = to[0] + width;
    const mid = (from[0] + x2) / 2;
    const path = `M${from[0]} ${y1} C${mid} ${y1 - 60} ${mid} ${y2 - 60} ${x2} ${y2}`;
    return { path, middle: [mid, (y1 + y2) / 2 - 45] };
  }
  const x1 = from[0] + width;
  const bulge = x1 + 46 + Math.min(60, Math.abs(y2 - y1) / 6);
  return {
    path: `M${x1} ${y1} C${bulge} ${y1} ${bulge} ${y2} ${x1} ${y2}`,
    middle: [x1 + (bulge - x1) * 0.75, (y1 + y2) / 2],
  };
}

export function layoutMap(model: Model): MapLayout {
  const count = model.graph.components.length;
  const band = bandsOf(model);
  const bands = Math.max(0, ...band) + 1;
  const columns: number[][] = Array.from({ length: bands }, () => []);
  model.stats.forEach((_, index) => columns[band[index]].push(index));
  const calls = new Map(model.flows.map((flow) => [flow.from * count + flow.to, flow.calls]));
  const rank = new Map<number, number>();
  columns.forEach((column, level) => {
    if (level > 0) {
      const centre = (target: number): number => {
        let sum = 0;
        let weight = 0;
        for (let caller = 0; caller < count; caller += 1) {
          const share = calls.get(caller * count + target) ?? 0;
          if (band[caller] < level && share > 0 && rank.has(caller)) {
            sum += (rank.get(caller) ?? 0) * share;
            weight += share;
          }
        }
        return weight > 0 ? sum / weight : 1e9;
      };
      column.sort((a, b) => centre(a) - centre(b));
    }
    column.forEach((component, row) => rank.set(component, row));
  });
  const tallest = Math.max(...columns.map((column) => column.length));
  const { width, height, gapX, gapY, left, top } = MAP_CARD;
  const positions: (readonly [number, number])[] = new Array(count);
  columns.forEach((column, level) => {
    const offset = ((tallest - column.length) * (height + gapY)) / 2;
    column.forEach((component, row) => {
      positions[component] = [left + level * (width + gapX), top + offset + row * (height + gapY)];
    });
  });
  const strongest = Math.max(1, ...model.flows.map((flow) => flow.calls));
  const lines = [...model.flows]
    .sort((a, b) => a.calls - b.calls)
    .map<MapLine>((flow) => {
      const { path, middle } = curve(positions[flow.from], positions[flow.to], band[flow.from], band[flow.to]);
      return {
        from: flow.from,
        to: flow.to,
        calls: flow.calls,
        partial: flow.partial,
        path,
        width: 0.8 + Math.log10(flow.calls + 1) * 1.5,
        strong: flow.calls >= strongest * STRONG_SHARE,
        labeled: flow.calls >= strongest * LABEL_SHARE,
        mostlyPartial: flow.partial / flow.calls >= MOSTLY_PARTIAL,
        middle,
      };
    });
  return {
    bandNames: BAND_NAMES[bands] ?? BAND_NAMES[3],
    band,
    positions,
    width: Math.max(left + bands * (width + gapX) - gapX + 120, 900),
    height: Math.max(tallest * (height + gapY) + 130, 520),
    lines,
  };
}
