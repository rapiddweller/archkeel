export const literal = () => import("./lib");
export const quoted = () => import('./types');
export const template = () => import(`./side`);
export const interpolated = (name: string) => import(`./${name}`);
export const conditional = (on: boolean) => (on ? import("./lib") : import("./types"));
export async function waited() {
  const lib = await import("./lib");
  const [side] = await Promise.all([import("./side")]);
  return [lib, side];
}
export const computed = (name: string) => import(name);
export const absent = () => import("./gone");
