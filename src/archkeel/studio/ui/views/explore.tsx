/** AD-290: Explore: the Explorer of the snapshot and the component that the user selects. */
import { useState } from "preact/hooks";
import { EXPLORER_PAGE, StudioState } from "../api";
import { ExplorerCanvas, SelectedComponent } from "../canvas";
import { Page, Panel } from "../components";
import { ExploreState } from "../vocabulary";

export function Explore(props: { state: StudioState }) {
  const [selected, setSelected] = useState<SelectedComponent | null>(null);
  if (props.state.explore !== ExploreState.DONE) {
    return (
      <Page title="Explore the code as it is" lead="No map yet. Overview shows the progress.">
        {null}
      </Page>
    );
  }
  return (
    <Page
      title="Explore the code as it is"
      lead="The Explorer of archkeel explore: modules and imports, each with its evidence."
    >
      <div class="explore">
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
