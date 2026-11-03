/** AD-290: Explore: the Explorer of the snapshot, once explore is done. */
import { EXPLORER_PAGE, StudioState } from "../api";
import { ExplorerCanvas } from "../canvas";
import { Page } from "../components";
import { ExploreState } from "../vocabulary";

export function Explore(props: { state: StudioState }) {
  const done = props.state.explore === ExploreState.DONE;
  return (
    <Page
      title="Explore the code as it is"
      lead="The Explorer of archkeel explore: modules and imports, each with its evidence."
    >
      {done ? (
        <ExplorerCanvas src={EXPLORER_PAGE} />
      ) : (
        <p>No map yet. Overview shows the progress.</p>
      )}
    </Page>
  );
}
