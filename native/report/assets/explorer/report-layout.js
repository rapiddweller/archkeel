"use strict";
// The routes of the UML relationships between placed boxes: ports on the box edges, lanes between
// rows, and paths that keep clear of frame headers and of each other. report-placement.js places
// the boxes; this file draws the lines between them and publishes both as ArchkeelReportLayout.
(function (global) {
  const placement = global.ArchkeelReportPlacement;
  const { orthogonalPath } = placement;
  function routeUmlRelationships(geometry) {
    const { positions, nodeSizes, edges, frames, cardWidth, gap, laneGap, rowGap } = geometry;
    function groupBy(items, keyOf) {
      const groups = new Map();
      for (const item of items) {
        const key = keyOf(item);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(item);
      }
      return groups;
    }

    function sizeOf(id) {
      const size = nodeSizes[id];
      if (size) return size;
      const frame = frames[id];
      return frame && { width: frame.right - frame.left, height: frame.bottom - frame.top };
    }

    function portX(node, index, count) {
      const width = sizeOf(node).width;
      const inset = Math.min(24, width / 4);
      const span = width - 2 * inset;
      const at = count === 1 ? span / 2 : (span * index) / (count - 1);
      return positions[node].x + inset + at;
    }

    function laneKey(edge) {
      return [positions[edge.source].y, positions[edge.target].y].sort((a, b) => a - b).join(":");
    }

    function laneOffsetFor(edge, lanes) {
      const lane = lanes.get(laneKey(edge));
      const index = lane.indexOf(edge);
      if (positions[edge.source].y === positions[edge.target].y) return index * laneGap;
      return (index - (lane.length - 1) / 2) * laneGap;
    }

    function routePointsClear(points, headers, padding) {
      for (let index = 1; index < points.length; index += 1) {
        const [x1, y1] = points[index - 1];
        const [x2, y2] = points[index];
        for (const header of headers) {
          const left = header.left - padding;
          const right = header.right + padding;
          const top = header.top - padding;
          const bottom = header.bottom + padding;
          if (x1 === x2 && x1 > left && x1 < right
              && Math.max(y1, y2) > top && Math.min(y1, y2) < bottom) return false;
          if (y1 === y2 && y1 > top && y1 < bottom
              && Math.max(x1, x2) > left && Math.min(x1, x2) < right) return false;
        }
      }
      return true;
    }

    function protectedFrameHeaders(bounds) {
      return Object.values(bounds).map((frame) => ({
        left: frame.left,
        right: frame.right,
        top: frame.top,
        bottom: frame.top + frame.header,
      }));
    }

    function routeFor(
      edge, outIndex, inIndex, outCount, inCount, laneOffset, headers, frames, occupied, laneIndex,
    ) {
      const sourceFrame = frames[edge.source];
      const targetFrame = frames[edge.target];
      const otherSourceX = positions[edge.target].x + cardWidth / 2;
      const otherTargetX = positions[edge.source].x + cardWidth / 2;
      const frameAnchor = (frame, otherX) => ({
        x: otherX < (frame.left + frame.right) / 2 ? frame.left : frame.right,
        y: frame.top + frame.header + 10,
      });
      const sourceAnchor = sourceFrame ? frameAnchor(sourceFrame, otherSourceX) : null;
      const targetAnchor = targetFrame ? frameAnchor(targetFrame, otherTargetX) : null;
      const sx = sourceAnchor?.x ?? portX(edge.source, outIndex, outCount);
      const tx = targetAnchor?.x ?? portX(edge.target, inIndex, inCount);
      const sPos = positions[edge.source];
      const tPos = positions[edge.target];
      const sameRow = !sourceFrame && !targetFrame && sPos.y === tPos.y;
      const sourceHeight = sizeOf(edge.source).height, targetHeight = sizeOf(edge.target).height;
      const sy = sourceAnchor?.y;
      const ty = targetAnchor?.y;
      const upward = (ty ?? tPos.y) < (sy ?? sPos.y);
      if (sameRow) {
        const sy = sPos.y + sourceHeight;
        const targetBottom = tPos.y + targetHeight;
        const drop = Math.max(sy, targetBottom) + 56 + laneOffset;
        const end = targetBottom;
        const points = [[sx, sy], [sx, drop], [tx, drop], [tx, end]];
        const direct = {
          d: orthogonalPath(points),
          mid: [(sx + tx) / 2, drop], end: [tx, end],
        };
        return routeAroundHeaders(
          direct, points, sx, sy, tx, end, headers, edge, frames, occupied, laneIndex, inIndex,
        );
      }
      const startY = sy ?? (upward ? sPos.y : sPos.y + sourceHeight);
      const endY = ty ?? (upward ? tPos.y + targetHeight : tPos.y);
      const my = (startY + endY) / 2 + laneOffset;
      const end = endY;
      const frameSideLead = (frame, anchor) => [
        anchor.x + (anchor.x === frame.left ? -14 : 14), anchor.y,
      ];
      const start = [sx, startY];
      const finish = [tx, end];
      const sourceLead = sourceAnchor ? frameSideLead(sourceFrame, sourceAnchor) : null;
      const targetLead = targetAnchor ? frameSideLead(targetFrame, targetAnchor) : null;
      const points = [
        start,
        ...(sourceLead ? [sourceLead, [sourceLead[0], my]] : [[sx, my]]),
        ...(targetLead ? [[targetLead[0], my], targetLead, finish] : [[tx, my], finish]),
      ];
      const direct = {
        d: orthogonalPath(points),
        mid: [(sx + tx) / 2, my],
        end: finish,
      };
      return routeAroundHeaders(
        direct, points, sx, startY, tx, end, headers, edge, frames, occupied, laneIndex, inIndex,
      );
    }

    function sharedRouteLength(points, occupied, limit = Infinity, clearance = laneGap, avoidCrossings = false) {
      let total = 0;
      for (let i = 1; i < points.length; i += 1) {
        const [ax, ay] = points[i - 1], [bx, by] = points[i];
        const vertical = ax === bx;
        if (!vertical && ay !== by) continue;
        const axis = vertical ? occupied.vertical : occupied.horizontal;
        const at = vertical ? ax : ay;
        const start = Math.min(vertical ? ay : ax, vertical ? by : bx);
        const end = Math.max(vertical ? ay : ax, vertical ? by : bx);
        if (avoidCrossings) {
          const perpendicular = vertical ? occupied.horizontal : occupied.vertical;
          for (const segments of perpendicular.values()) {
            for (const segment of segments) {
              if (segment.at >= start && segment.at <= end && at >= segment.start && at <= segment.end) {
                total += laneGap;
              }
              if (total > limit) return total;
            }
          }
        }
        const key = Math.floor(at / laneGap);
        // Only nearby parallel segments can share a stretch.
        for (const bucket of [key - 1, key, key + 1]) {
          for (const segment of axis.get(bucket) || []) {
            if (Math.abs(at - segment.at) >= clearance) continue;
            const overlap = Math.min(end, segment.end) - Math.max(start, segment.start);
            if (overlap > 0) total += overlap;
            // Equality must finish scoring before the caller can compare tied candidates.
            if (total > limit) return total;
          }
        }
      }
      return total;
    }

    function routeAroundHeaders(
      direct, points, sx, sy, tx, end, headers, edge, frames, occupied, laneIndex, targetPortIndex,
    ) {
      const avoidCrossings = occupied.callFan;
      const cards = Object.entries(positions).filter(([id, position]) =>
        !frames[id] && Number.isFinite(position.x) && Number.isFinite(position.y));
      const cardBounds = cards.map(([id, position]) => ({
        left: position.x, right: position.x + cardWidth,
        top: position.y, bottom: position.y + sizeOf(id).height,
      }));
      if (routePointsClear(points, headers, 10)
          && routePointsClear(points, cardBounds, 0)
          && sharedRouteLength(points, occupied, 1, laneGap, avoidCrossings) === 0) return { ...direct, points };
      const allLeft = Math.min(...[
        ...headers.map((header) => header.left),
        ...cards.map(([, position]) => position.x),
      ]);
      const allRight = Math.max(...[
        ...headers.map((header) => header.right),
        ...cards.map(([, position]) => position.x + cardWidth),
      ]);
      const gutters = [...new Set([
        ...headers.flatMap((header) => [header.left - 14, header.right + 14]),
        ...cardBounds.flatMap((card) => [card.left - gap / 3, card.right + gap / 3]),
        allLeft - 14, allRight + 14,
        allLeft - 14 - (laneIndex + 1) * laneGap,
        allRight + 14 + (laneIndex + 1) * laneGap,
      ])];
      const sourceCard = frames[edge.source] ? null : positions[edge.source];
      const targetCard = frames[edge.target] ? null : positions[edge.target];
      const sourceHeight = sizeOf(edge.source).height, targetHeight = sizeOf(edge.target).height;
      const sourceDirection = sourceCard ? Math.sign(sy - sourceCard.y - sourceHeight / 2)
        : Math.sign(points[1]?.[1] - sy) || Math.sign(end - sy) || 1;
      const endDirection = targetCard ? Math.sign(targetCard.y + targetHeight / 2 - end)
        : Math.sign(end - points.at(-2)?.[1]) || Math.sign(end - sy) || 1;
      // Separate arrival heights keep dependencies from sharing their final rail.
      const lead = 14 + Math.min(targetPortIndex * laneGap, Math.max(0, Math.abs(end - sy) / 2 - 14));
      const normalSource = frames[edge.source]
        ? { point: [sx, sy], lead: points[1], axis: "horizontal" }
        : { point: [sx, sy], lead: [sx, sy + sourceDirection * 14], axis: "vertical" };
      const normalTarget = frames[edge.target]
        ? { point: [tx, end], lead: points.at(-2), axis: "horizontal" }
        : { point: [tx, end], lead: [tx, end - endDirection * lead], axis: "vertical" };
      if (normalTarget.axis === "vertical" && !routePointsClear(
          [normalTarget.lead, normalTarget.point], cardBounds, 0)) {
        normalTarget.lead = [tx, end - endDirection * 14];
      }
      const sourceBlocked = !routePointsClear(
        [normalSource.point, normalSource.lead], headers, 2,
      ) || !routePointsClear([normalSource.point, normalSource.lead], cardBounds, 0);
      const targetBlocked = !routePointsClear(
        [normalTarget.lead, normalTarget.point], headers, 2,
      ) || !routePointsClear([normalTarget.lead, normalTarget.point], cardBounds, 0);
      const sidePorts = (card, height, x) => ["left", "right"].flatMap((side) => {
        const at = side === "left" ? card.x : card.x + cardWidth;
        const y = card.y + 14 + (height - 28) * (x - card.x) / cardWidth;
        // Opposite turns from nearby side ports need separate vertical lanes.
        return [gap / 2, gap / 2 + laneGap].map((distance) => ({ point: [at, y],
          lead: [at + (side === "left" ? -distance : distance), y], axis: "horizontal" }));
      });
      const sourcePorts = sourceBlocked && sourceCard
        ? sidePorts(sourceCard, sourceHeight, sx) : [normalSource];
      const clearance = occupied.clearance;
      const barriers = [...headers.map((header) => ({
        left: header.left - 2, right: header.right + 2,
        top: header.top - 2, bottom: header.bottom + 2,
      })), ...cardBounds];
      const clearSegments = (points) => {
        for (let index = 1; index < points.length; index += 1) {
          const [ax, ay] = points[index - 1], [bx, by] = points[index];
          const vertical = ax === bx;
          if (!vertical && ay !== by) continue;
          const at = vertical ? ax : ay;
          const axis = vertical ? clearance.vertical : clearance.horizontal;
          // Fixed card/header bounds are shared by every route in this render.
          if (!axis.has(at)) axis.set(at, barriers.filter((barrier) => vertical
            ? at > barrier.left && at < barrier.right
            : at > barrier.top && at < barrier.bottom));
          const start = Math.min(vertical ? ay : ax, vertical ? by : bx);
          const end = Math.max(vertical ? ay : ax, vertical ? by : bx);
          if (axis.get(at).some((barrier) => vertical
            ? end > barrier.top && start < barrier.bottom
            : end > barrier.left && start < barrier.right)) return false;
        }
        return true;
      };
      let route = null, leastShared = Infinity, leastNearby = Infinity;
      // Most routes need no expanded search; retry only when every clear route shares a stretch.
      for (const pass of [
        { expanded: false, sideRetry: false },
        { expanded: true, sideRetry: false },
        { expanded: true, sideRetry: true },
      ]) {
        const { expanded, sideRetry } = pass;
        const sources = sideRetry
          ? sourceCard ? sidePorts(sourceCard, sourceHeight, sx) : [] : sourcePorts;
        const distances = expanded
          ? Array.from({ length: Math.ceil((rowGap - 14) / (laneGap / 2)) }, (_, index) => 14 + index * laneGap / 2)
          : [14, 14 + laneGap];
        const offsets = expanded ? [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2] : [-1, 0, 1];
        const targetPorts = [
          ...(!targetBlocked ? [normalTarget, ...(normalTarget.axis === "vertical"
            ? distances.map((distance) => ({ ...normalTarget,
              lead: [tx, end - endDirection * distance] }))
              .filter((port) => port.lead[1] !== normalTarget.lead[1]) : [])] : []),
          ...(targetCard && (targetBlocked || expanded) ? sidePorts(targetCard, targetHeight, tx) : []),
        ];
        const sourceLanes = [...new Set([
          ...[...(sideRetry ? sources.map((port) => port.lead[1]) : [normalSource.lead[1]]), normalTarget.lead[1]]
            .flatMap((y) => offsets.map((offset) => y + offset * laneGap)),
          ...cards.flatMap(([id, position]) => [
            position.y - 14, position.y + sizeOf(id).height + 14,
          ]).flatMap((y) => offsets.map((offset) => y + offset * laneGap)),
          ...headers.flatMap((header) => [header.top - 14, header.bottom + 14]),
        ])];
        const occupiedX = [...occupied.vertical.values()].flat().map((segment) => segment.at);
        const candidateGutters = expanded ? [...new Set([...gutters,
          ...(sideRetry ? [
            Math.min(allLeft - 14, ...occupiedX) - laneGap,
            Math.max(allRight + 14, ...occupiedX) + laneGap,
          ] : []),
          ...cardBounds.flatMap((card) => Array.from(
            { length: Math.floor(gap / (laneGap / 2)) - 1 }, (_, index) => {
              const offset = (index + 1) * laneGap / 2;
              return [card.left - offset, card.right + offset];
            }).flat()),
        ])] : gutters;
        candidateGutters.sort((a, b) => Math.abs(sx - a) + Math.abs(tx - a)
          - Math.abs(sx - b) - Math.abs(tx - b));
        sourceLanes.sort((a, b) => Math.abs(sy - a) + Math.abs(end - a)
          - Math.abs(sy - b) - Math.abs(end - b));
        candidates: for (const source of sources) {
          // Overlapping fixed segments cannot become a clear route by changing its middle.
          const exits = sourceLanes.filter((laneY) => !(source.axis === "vertical"
            && (laneY - source.lead[1]) * sourceDirection < 0)
            && clearSegments([source.point, source.lead, [source.lead[0], laneY]])
            && (!sideRetry || sharedRouteLength([source.point, source.lead, [source.lead[0], laneY]],
              occupied, 1, laneGap / 2, avoidCrossings) === 0))
            .map((laneY) => ({ laneY, shared: sharedRouteLength(
              [source.point, source.lead, [source.lead[0], laneY]],
              occupied, Infinity, laneGap / 2, avoidCrossings), nearby: sharedRouteLength(
              [source.point, source.lead, [source.lead[0], laneY]],
              occupied, Infinity, laneGap, avoidCrossings) }));
          // Horizontal departures are independent of the target's arrival height.
          const departures = new Map(candidateGutters.map((x) => [x, exits.filter(({ laneY }) =>
            clearSegments([[source.lead[0], laneY], [x, laneY]]))
            .map((exit) => {
              const segment = [[source.lead[0], exit.laneY], [x, exit.laneY]];
              return { laneY: exit.laneY,
                shared: exit.shared + sharedRouteLength(segment, occupied, Infinity, laneGap / 2, avoidCrossings),
                nearby: exit.nearby + sharedRouteLength(segment, occupied, Infinity, laneGap, avoidCrossings) };
            })]));
          for (const target of targetPorts) {
            const arrivals = candidateGutters.filter((x) => clearSegments([
              [x, target.lead[1]], target.lead, target.point,
            ]) && (!sideRetry || sharedRouteLength([[x, target.lead[1]], target.lead, target.point],
              occupied, 1, laneGap / 2, avoidCrossings) === 0))
              .map((gutterX) => ({ gutterX, shared: sharedRouteLength(
                [[gutterX, target.lead[1]], target.lead, target.point],
                occupied, Infinity, laneGap / 2, avoidCrossings), nearby: sharedRouteLength(
                [[gutterX, target.lead[1]], target.lead, target.point],
                occupied, Infinity, laneGap, avoidCrossings) }));
            for (const arrival of arrivals) {
              if (arrival.shared > leastShared) continue;
              const { gutterX } = arrival;
              for (const exit of departures.get(gutterX)) {
                // The middle cannot reduce overlap already fixed at either endpoint.
                if (exit.shared + arrival.shared > leastShared) continue;
                const { laneY } = exit;
                const points = [
                  source.point, source.lead, [source.lead[0], laneY], [gutterX, laneY],
                  [gutterX, target.lead[1]], target.lead, target.point,
                ];
                // Only the vertical middle remains after departures and arrivals.
                if (!clearSegments(points.slice(3, 5))) continue;
                const fixedShared = exit.shared + arrival.shared;
                const shared = fixedShared + sharedRouteLength(points.slice(3, 5), occupied,
                  Math.max(1, leastShared - fixedShared), laneGap / 2, avoidCrossings);
                if (shared > leastShared || sideRetry && shared > 0) continue;
                const fixedNearby = exit.nearby + arrival.nearby;
                const nearby = fixedNearby + sharedRouteLength(points.slice(3, 5), occupied,
                  shared === leastShared ? Math.max(1, leastNearby - fixedNearby) : Infinity,
                  laneGap, avoidCrossings);
                const length = points.slice(1).reduce((total, point, index) => total
                  + Math.abs(point[0] - points[index][0]) + Math.abs(point[1] - points[index][1]), 0);
                if (shared < leastShared || nearby < leastNearby
                    || shared === leastShared && nearby === leastNearby && length < route.length) {
                  route = { points, end: target.point, length };
                  leastShared = shared; leastNearby = nearby;
                }
                if (shared === 0) break candidates;
              }
            }
          }
        }
        if (leastShared === 0) break;
      }
      if (!route) return { ...direct, points, routingWarning: true };
      return {
        d: orthogonalPath(route.points),
        mid: route.points[Math.floor(route.points.length / 2)],
        end: route.end,
        points: route.points,
      };
    }

    for (const edge of edges) {
      if (!positions[edge.source] || !positions[edge.target] || !sizeOf(edge.source) || !sizeOf(edge.target)) {
        throw new Error(`UML relationship ${edge.id} has a missing layout endpoint.`);
      }
    }
    const callFan = edges.length > 0 && edges.every((edge) =>
      edge.relationshipKind === "calls" && edge.source === edges[0].source);
    // Both directions share a card side; separate degree tables would reuse its ports.
    const endpoints = edges.flatMap((edge) => {
      const upward = positions[edge.target].y < positions[edge.source].y;
      const sameRow = positions[edge.source].y === positions[edge.target].y;
      return [
        { edge, end: "source", node: edge.source, other: edge.target,
          side: upward ? "top" : "bottom" },
        { edge, end: "target", node: edge.target, other: edge.source,
          side: upward || sameRow ? "bottom" : "top" },
      ];
    });
    const ports = groupBy(endpoints, (port) => `${port.node}:${port.side}`);
    ports.forEach((ports) => ports.sort((a, b) => {
      const ax = positions[a.other].x - positions[a.node].x;
      const bx = positions[b.other].x - positions[b.node].x;
      // Deeper callees need the outer ports to pass around the nearer row.
      const depth = callFan && a.end === "source" && b.end === "source" && ax * bx > 0
        ? Math.sign(ax) * (Math.abs(positions[a.other].y - positions[a.node].y)
          - Math.abs(positions[b.other].y - positions[b.node].y)) : 0;
      return depth || ax - bx || a.edge.id.localeCompare(b.edge.id) || a.end.localeCompare(b.end);
    }));
    const lanes = groupBy(edges, laneKey);
    // Outer targets first reduces crossings between one caller's outgoing lines.
    lanes.forEach((edges) => edges.sort((a, b) => positions[a.source].x - positions[b.source].x
      || Math.abs(positions[b.target].x - positions[b.source].x)
        - Math.abs(positions[a.target].x - positions[a.source].x)
      || positions[a.target].x - positions[b.target].x));
    const routes = [];
    const occupied = { vertical: new Map(), horizontal: new Map(),
      clearance: { vertical: new Map(), horizontal: new Map() }, callFan };
    edges.forEach((edge, index) => {
      const source = endpoints[index * 2], target = endpoints[index * 2 + 1];
      const out = ports.get(`${source.node}:${source.side}`);
      const into = ports.get(`${target.node}:${target.side}`);
      const lane = lanes.get(laneKey(edge));
      const route = routeFor(edge, out.indexOf(source), into.indexOf(target), out.length, into.length,
        laneOffsetFor(edge, lanes), protectedFrameHeaders(frames), frames,
        occupied, lane.indexOf(edge));
      routes.push({ edgeId: edge.id, ...route });
      for (let i = 1; i < route.points.length; i += 1) {
        const [ax, ay] = route.points[i - 1], [bx, by] = route.points[i];
        const vertical = ax === bx;
        if (!vertical && ay !== by) continue;
        const axis = vertical ? occupied.vertical : occupied.horizontal;
        const at = vertical ? ax : ay;
        const key = Math.floor(at / laneGap);
        if (!axis.has(key)) axis.set(key, []);
        axis.get(key).push({ at,
          start: Math.min(vertical ? ay : ax, vertical ? by : bx),
          end: Math.max(vertical ? ay : ax, vertical ? by : bx) });
      }
    });
    return routes;
  }

  global.ArchkeelReportLayout = {
    layout: placement.layout, decodeLayout: placement.decodeLayout,
    buildAtlasGraph: placement.buildAtlasGraph, layoutUml: placement.layoutUml,
    layoutAtlas: placement.layoutAtlas, routeUmlRelationships,
    hasCompleteManualPositions: placement.hasCompleteManualPositions,
  };
})(window);
