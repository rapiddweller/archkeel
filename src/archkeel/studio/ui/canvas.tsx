/** AD-290: the Explorer island. The shell mounts the offline Explorer page; it never edits it. */
export function ExplorerCanvas(props: { src: string }) {
  // Slice 1 is always dark, as the Figma screens are.
  return <iframe title="Explorer" src={`${props.src}?theme=dark`} />;
}
