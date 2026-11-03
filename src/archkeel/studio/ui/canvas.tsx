/** AD-290: the Explorer island. The shell mounts the offline Explorer page; it never edits it. */
export function ExplorerCanvas(props: { src: string }) {
  const theme = matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
  return <iframe title="Explorer" src={`${props.src}?theme=${theme}`} />;
}
