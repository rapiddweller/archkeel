/** AD-290: Overview: the state of the snapshot and of the contract, from the API only. */
import { StudioState } from "../api";
import { Card, Page, Tabs } from "../components";
import { Evidence } from "../evidence";
import { ContractState, ExploreState } from "../vocabulary";

function Snapshot(props: { state: StudioState }) {
  const { explore, seconds, exit_code, notes } = props.state;
  if (explore === ExploreState.DONE) {
    return (
      <p>
        Map ready in {seconds} s. <a href="#/explore">Open Explore</a>.
      </p>
    );
  }
  if (explore === ExploreState.FAILED) {
    return (
      <>
        <p>archkeel explore stopped with exit code {exit_code}.</p>
        <ul>
          {notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
        <p>Correct the cause, then start archkeel studio again.</p>
      </>
    );
  }
  return <p>Making the map: {seconds} s. A large repository takes about 2 minutes.</p>;
}

const CONTRACT_TEXT: Record<ContractState, string> = {
  [ContractState.NOT_CONFIGURED]:
    "No contract: a policy verdict does not apply. archkeel init drafts one; " +
    "archkeel init --adopt adopts the code as it is.",
  [ContractState.INVALID]: "archkeel.toml does not load. archkeel validate names the reason.",
  [ContractState.CONFIGURED]:
    "archkeel report shows the contract, the deviations and PASS or FAIL.",
};

export function Overview(props: { state: StudioState }) {
  const configured = props.state.contract === ContractState.CONFIGURED;
  return (
    <Page
      title="Understand the codebase"
      lead="Observed map. A contract is not necessary. An import is not a runtime call."
    >
      <Tabs
        tabs={[
          { evidence: Evidence.Observed, text: "As-Is / Observed" },
          configured
            ? { evidence: Evidence.Target, text: "Target: contract" }
            : { evidence: Evidence.Claim, text: "Target unavailable" },
        ]}
      />
      <div class="cards">
        <Card title={`Snapshot of ${props.state.root_name}`} evidence={Evidence.Observed}>
          <Snapshot state={props.state} />
        </Card>
        <Card title="Contract" evidence={Evidence.Target}>
          <p>{CONTRACT_TEXT[props.state.contract]}</p>
        </Card>
      </div>
    </Page>
  );
}
