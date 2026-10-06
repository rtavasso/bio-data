import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ModerateParticipant, ModeratePost } from "./Moderation";

type Call = { url: string; init?: RequestInit };

function serve(permissions: string[]) {
  const calls: Call[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const body = url === "/api/me" ? { id: "operator", name: "operator", kind: "operator", permissions } : { state: "hidden" };
    return new Response(JSON.stringify(body), { status: 200 });
  }) as typeof fetch;
  return calls;
}

test("operators hide a post with a public reason; the write carries the CSRF header", async () => {
  const calls = serve(["read", "hide", "suspend"]);
  render(<ModeratePost post="post_x" hidden={false} />);
  fireEvent.click(await screen.findByText("Hide (operator)"));
  fireEvent.change(screen.getByLabelText("Public reason"), { target: { value: "off-topic" } });
  fireEvent.click(screen.getByRole("button", { name: "Hide" }));
  await screen.findByText("Recorded.");
  const write = calls.find((c) => c.url === "/api/moderation/hide")!;
  expect(JSON.parse(String(write.init?.body))).toEqual({ post: "post_x", reason: "off-topic" });
  expect((write.init?.headers as Record<string, string>)["X-Colloquy-Request"]).toBe("1");
});

test("a hidden post offers unhide; people without the permission see nothing", async () => {
  serve(["read", "hide"]);
  const { unmount } = render(<ModeratePost post="post_x" hidden />);
  expect(await screen.findByText("Unhide (operator)")).toBeTruthy();
  unmount();
  serve(["read", "post", "mark"]);
  const { container } = render(<><ModeratePost post="post_x" hidden={false} /><ModerateParticipant participant="agent_a" /></>);
  await waitFor(() => expect((globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(0));
  expect(container.textContent).toBe("");
});

test("operators suspend or reinstate a participant", async () => {
  const calls = serve(["read", "suspend"]);
  render(<ModerateParticipant participant="agent_a" />);
  fireEvent.click(await screen.findByText("Suspend or reinstate (operator)"));
  fireEvent.change(screen.getByLabelText("Moderation action"), { target: { value: "reinstate" } });
  fireEvent.change(screen.getByLabelText("Public reason"), { target: { value: "appeal accepted" } });
  fireEvent.click(screen.getByRole("button", { name: "Reinstate" }));
  await screen.findByText("Recorded.");
  expect(JSON.parse(String(calls.find((c) => c.url === "/api/moderation/reinstate")!.init?.body))).toEqual({
    participant: "agent_a", reason: "appeal accepted" });
});
