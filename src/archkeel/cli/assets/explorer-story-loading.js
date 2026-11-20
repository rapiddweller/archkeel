import { api } from "./studio-api.js";
import { button, cards, details, element, get, showError, viewport } from "./studio-dom.js";
import { state } from "./studio-state.js";
import { selectionHeading } from "./explorer.js";
import { setStoryLink } from "./explorer-map.js";
import { goToStoryStep, openCheckedStory, stopStoryPlayback, storyChat, storyHeading, storyMode, storyView, } from "./explorer-story.js";
export async function showStories() {
    const context = get("map").getAttribute("aria-pressed") === "true"
        ? state.selected : storyView.context;
    const request = ++state.request;
    stopStoryPlayback();
    let result;
    try {
        result = await api("stories");
    }
    catch (error) {
        if (request === state.request)
            showError(error, showStories);
        return;
    }
    if (request !== state.request)
        return;
    storyView.context = context;
    storyMode();
    setStoryLink(null);
    storyHeading();
    get("story-controls").hidden = true;
    viewport.scrollTo(0, 0);
    selectionHeading("Story library", "Story");
    details.append(storyChat());
    const list = element("section", "", "story-library");
    if (!result.items.length)
        list.append(element("p", "No saved stories. Draft one with chat, or follow a call from Architecture."));
    for (const item of result.items)
        list.append(button(item.title ?? item.id, () => loadStory(item.id), "detail-btn"));
    cards.replaceChildren(list);
}
export async function loadStory(id) {
    const request = ++state.request;
    stopStoryPlayback();
    let story;
    try {
        story = await api("stories", { id });
    }
    catch (error) {
        if (request === state.request)
            showError(error, () => loadStory(id));
        return;
    }
    if (request === state.request)
        await openCheckedStory(story);
}
export async function showStory(id, index = -1, follow = false) {
    const request = ++state.request;
    stopStoryPlayback();
    let result;
    try {
        result = await api("story", { id });
    }
    catch (error) {
        if (request === state.request)
            showError(error, () => showStory(id, index, follow));
        return;
    }
    if (request !== state.request)
        return;
    storyMode();
    if (storyView.saved)
        state.hops = [];
    storyView.saved = null;
    setStoryLink(null);
    storyHeading("Call sequence");
    const [step] = result.items;
    if (!step) {
        cards.replaceChildren(element("p", result.reason ?? "No call evidence for this step.", "unknown"));
        details.replaceChildren();
        get("story-controls").hidden = true;
        return;
    }
    if (follow) {
        state.hops = [...state.hops.slice(0, state.storyIndex + 1), step];
        index = state.hops.length - 1;
    }
    else if (index < 0 || !state.hops.length) {
        state.hops = [step];
        index = 0;
        viewport.scrollTo(0, 0);
    }
    return goToStoryStep(index);
}
