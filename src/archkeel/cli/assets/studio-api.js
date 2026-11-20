export async function api(operation, args = {}) {
    const query = new URLSearchParams();
    for (const [key, value] of Object.entries(args)) {
        if (value != null)
            query.set(key, String(value));
    }
    const response = await fetch("/api/v1/" + operation + "?" + query);
    if (!response.ok)
        throw new Error(await response.text());
    return response.json();
}
export async function draftStory(body) {
    const reply = await fetch("/api/v1/story-chat", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!reply.ok) {
        const result = await reply.json();
        throw new Error(result.error ?? "Story drafting failed.");
    }
    return reply.json();
}
