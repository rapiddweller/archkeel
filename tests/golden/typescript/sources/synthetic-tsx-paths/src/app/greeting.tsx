import React from "react";
import { join, SEPARATOR } from "@util/format";
import type { Label } from "@util/format";

interface Props {
  names: string[];
  label?: Label;
}

export class Badge extends React.Component<Props> {
  render() {
    return <span title={SEPARATOR}>{join(this.props.names)}</span>;
  }
}

export function Greeting({ names, label }: Props) {
  const kind = label?.text === "formal" ? "Dear" : "Hi";
  return (
    <div className="greeting">
      <Badge names={names} />
      {kind}
    </div>
  );
}
