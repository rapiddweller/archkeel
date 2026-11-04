/** AD-290: a pan and zoom surface for a drawing of known size. Props only. */
import type { ComponentChildren } from "preact";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";

interface Camera {
  readonly x: number;
  readonly y: number;
  readonly k: number;
}

const ZOOM_MIN = 0.1;
// A drawing that is much larger than the frame still fits whole.
const FIT_MIN = 0.03;
const ZOOM_MAX = 3;
const FIT_MAX = 1.2;
const FIT_PAD = 16;
const STEP_IN = 1.25;
const STEP_OUT = 0.8;
const KEY_PAN = 48;
const WHEEL = 0.0016;
const WHEEL_PINCH = 0.01;

const clamp = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value));
const isTyping = (target: EventTarget | null): boolean =>
  target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement;

export function Viewport(props: {
  width: number;
  height: number;
  label: string;
  /** The view fits again when this value changes. */
  fitKey: unknown;
  children: ComponentChildren;
}) {
  const frame = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; camera: Camera } | null>(null);
  // Until the user moves the view, a change of the frame (a panel opens, the window grows) fits again.
  const moved = useRef(false);
  const [camera, setCamera] = useState<Camera>({ x: 0, y: 0, k: 1 });

  const fit = (): void => {
    moved.current = false;
    // The layout size, not the drawn one: a zoom between levels scales the frame while it fits.
    const box = frame.current ? { width: frame.current.clientWidth, height: frame.current.clientHeight } : null;
    if (!box) return;
    const k = clamp(Math.min((box.width - 2 * FIT_PAD) / props.width, (box.height - 2 * FIT_PAD) / props.height), FIT_MIN, FIT_MAX);
    setCamera({ k, x: (box.width - props.width * k) / 2, y: Math.max(FIT_PAD, (box.height - props.height * k) / 2) });
  };
  useLayoutEffect(fit, [props.fitKey, props.width, props.height]);
  useEffect(() => {
    if (!frame.current) return;
    const watch = new ResizeObserver(() => moved.current || fit());
    watch.observe(frame.current);
    return () => watch.disconnect();
  }, [props.fitKey, props.width, props.height]);

  const zoom = (factor: number, anchorX?: number, anchorY?: number): void => {
    moved.current = true;
    setCamera((now) => {
      const box = frame.current?.getBoundingClientRect();
      const ax = anchorX ?? (box ? box.width / 2 : 0);
      const ay = anchorY ?? (box ? box.height / 2 : 0);
      const k = clamp(now.k * factor, ZOOM_MIN, ZOOM_MAX);
      const ratio = k / now.k;
      return { k, x: ax - (ax - now.x) * ratio, y: ay - (ay - now.y) * ratio };
    });
  };

  const pan = (x: number, y: number): void => {
    moved.current = true;
    setCamera((now) => ({ ...now, x: now.x + x, y: now.y + y }));
  };
  const keys: Record<string, () => void> = {
    "+": () => zoom(STEP_IN),
    "=": () => zoom(STEP_IN),
    "-": () => zoom(STEP_OUT),
    "0": fit,
    ArrowLeft: () => pan(KEY_PAN, 0),
    ArrowRight: () => pan(-KEY_PAN, 0),
    ArrowUp: () => pan(0, KEY_PAN),
    ArrowDown: () => pan(0, -KEY_PAN),
  };

  const pointer = (event: { clientX: number; clientY: number }): { x: number; y: number } => {
    const box = frame.current?.getBoundingClientRect();
    return { x: event.clientX - (box?.left ?? 0), y: event.clientY - (box?.top ?? 0) };
  };

  return (
    <div
      class="viewport"
      ref={frame}
      tabIndex={0}
      role="group"
      aria-label={props.label}
      onPointerDown={(event) => {
        // A card or a button takes its own click; only the empty surface pans.
        if (event.target instanceof Element && event.target.closest("a, button, input")) return;
        drag.current = { x: event.clientX, y: event.clientY, camera };
        frame.current?.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        const start = drag.current;
        if (start) {
          moved.current = true;
          setCamera({
            k: start.camera.k,
            x: start.camera.x + event.clientX - start.x,
            y: start.camera.y + event.clientY - start.y,
          });
        }
      }}
      onPointerUp={() => (drag.current = null)}
      onPointerCancel={() => (drag.current = null)}
      onWheel={(event) => {
        event.preventDefault();
        const at = pointer(event);
        zoom(Math.exp(-event.deltaY * (event.ctrlKey ? WHEEL_PINCH : WHEEL)), at.x, at.y);
      }}
      onKeyDown={(event) => {
        const action = keys[event.key];
        if (isTyping(event.target) || action === undefined) return;
        action();
        event.preventDefault();
      }}
    >
      <div
        class="stage"
        data-camera={`${camera.x.toFixed(0)},${camera.y.toFixed(0)},${camera.k.toFixed(3)}`}
        style={{
          width: `${props.width}px`,
          height: `${props.height}px`,
          transform: `translate(${camera.x}px, ${camera.y}px) scale(${camera.k})`,
        }}
      >
        {props.children}
      </div>
      <div class="zoom">
        <button type="button" aria-label="Zoom in" onClick={() => zoom(STEP_IN)}>
          +
        </button>
        <button type="button" aria-label="Zoom out" onClick={() => zoom(STEP_OUT)}>
          −
        </button>
        <button type="button" class="fit" onClick={fit}>
          Fit
        </button>
        <span>drag to pan · scroll to zoom · 0 = fit</span>
      </div>
    </div>
  );
}
