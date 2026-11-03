/** AD-290: a page that slice 1 does not build; it says what does the job today. */
import { Page } from "../components";

export function NotBuilt(props: { title: string; today: string }) {
  return (
    <Page title={props.title} lead="Not built in Studio yet.">
      <section class="card">
        <p>{props.today}</p>
      </section>
    </Page>
  );
}
