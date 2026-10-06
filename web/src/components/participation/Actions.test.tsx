import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MarkForm, PostForm, parsePointers } from "./Actions";
import { MarkList } from "./Marks";

type Call = { url: string; init?: RequestInit };

function capture(reply: (url: string) => [number, unknown]) {
  const calls: Call[] = [];
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init });
    const [status, body] = reply(String(input));
    return new Response(JSON.stringify(body), { status });
  }) as typeof fetch;
  return calls;
}

const header = (call: Call, name: string) => (call.init?.headers as Record<string, string>)[name];

test("pointers parse from kind:id[:locator] lists", () => {
  expect(parsePointers("artifact:artifact_1:row B, post:post_2")).toEqual([
    { kind: "artifact", id: "artifact_1", locator: "row B" }, { kind: "post", id: "post_2" },
  ]);
});

test("mark form posts attribution with the write header and explains refusals", async () => {
  const calls = capture(() => [429, { error: "rate_limited", detail: "marks per hour limit is 1" }]);
  render(<MarkForm targetKind="post" targetId="post_x" />);
  fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Opened the table" } });
  fireEvent.click(screen.getByRole("button", { name: "Mark" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", expect.stringContaining("Rate limit reached"));
  expect(header(calls[0], "X-Colloquy-Request")).toBe("1");
  expect(JSON.parse(String(calls[0].init?.body))).toMatchObject({ target_kind: "post", kind: "checked_source", note: "Opened the table" });
});

test("post form uploads raw bytes and attaches them as upload_ids", async () => {
  const upload = { id: "upload_1", blob: "a".repeat(64), name: "gel.png", uploader: "h", media_type: "image/png", size: 3, receipt_blob: "r", created: "t" };
  const calls = capture((url) => (url === "/api/uploads" ? [200, upload] : [200, { id: "post_new" }]));
  const done = vi.fn();
  const { container } = render(<PostForm onDone={done} />);
  fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Gel" } });
  fireEvent.change(screen.getByLabelText("Body"), { target: { value: "Attached." } });
  const file = new File([new Uint8Array([1, 2, 3])], "gel image.png", { type: "image/png" });
  fireEvent.change(container.querySelector("input[type=file]")!, { target: { files: [file] } });
  expect(await screen.findByText("gel.png")).toBeTruthy();
  const sent = calls.find((c) => c.url === "/api/uploads")!;
  expect(header(sent, "X-Filename")).toBe("gel%20image.png");
  expect(header(sent, "Content-Type")).toBe("image/png");
  expect(header(sent, "X-Colloquy-Request")).toBe("1");
  fireEvent.click(screen.getByRole("button", { name: "Post" }));
  await waitFor(() => expect(done).toHaveBeenCalledWith("post_new"));
  const created = calls.find((c) => c.url === "/api/posts")!;
  expect(JSON.parse(String(created.init?.body))).toMatchObject({ title: "Gel", upload_ids: ["upload_1"] });
});

test("marks render as attribution with pointers, never as a status", () => {
  render(
    <MemoryRouter>
      <MarkList marks={[{
        id: "mark_1", participant: "human_" + "1".repeat(32), participant_name: "mira", participant_kind: "human",
        target_kind: "post", target_id: "post_x", kind: "disputed", note: "Prose and table disagree.",
        pointers: [{ kind: "post", id: "post_" + "2".repeat(32) }], body_blob: "b", created: "2026-10-01T00:00:00+00:00",
        attribution_not_status: true,
      }]} />
    </MemoryRouter>,
  );
  expect(screen.getByText(/attribution, not status/)).toBeTruthy();
  expect(screen.getByText("disputed")).toBeTruthy();
  expect(screen.getByRole("link", { name: "post post_" + "2".repeat(32) }).getAttribute("href")).toBe("/post/post_" + "2".repeat(32));
});
