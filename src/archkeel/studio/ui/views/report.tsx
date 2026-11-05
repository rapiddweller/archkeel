/** AD-290: Report: the Explorer page of the snapshot and the component that the user selects. */
import { useState } from "preact/hooks";
import { EXPLORER_PAGE, StudioState } from "../api";
import { ExplorerCanvas, SelectedComponent } from "../canvas";
import { ExploreFailure, Page, Panel } from "../components";
import { ExploreState } from "../vocabulary";

export function Report(props: { state: StudioState }) {
  const [selected, setSelected] = useState<SelectedComponent | null>(null);
  if (props.state.explore !== ExploreState.DONE && props.state.explore !== ExploreState.INCOMPLETE) {
    const failed = props.state.explore === ExploreState.FAILED;
    return (
      <Page title="Report of the code as it is" lead="The Explorer page of archkeel explore.">
        {failed ? (
          <ExploreFailure exitCode={props.state.exit_code} notes={props.state.notes} />
        ) : (
          <p>Waiting for Explore to write a readable snapshot.</p>
        )}
      </Page>
    );
  }
  return (
    <Page
      title="Report of the code as it is"
      lead="The Explorer page of archkeel explore: modules and imports, each with its evidence."
    >
      {props.state.explore === ExploreState.INCOMPLETE ? (
        <p role="status">The source snapshot is incomplete; UNKNOWN means evidence is missing.</p>
      ) : null}
      <div class="report">
        <ExplorerCanvas src={EXPLORER_PAGE} onSelect={setSelected} />
        <Panel title="Selected component">
          {selected ? (
            <>
              <p>{selected.label ?? selected.id}</p>
              <p>
                <code>{selected.id}</code>
              </p>
            </>
          ) : (
            <p>Select a component in the Explorer.</p>
          )}
        </Panel>
      </div>
    </Page>
  );
}
