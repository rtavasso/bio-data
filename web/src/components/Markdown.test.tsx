import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { linkIdentifiers, Markdown } from "./Markdown";

const artifact = "artifact_" + "a".repeat(64);

test("identifiers outside code become in-app links; raw HTML and unsafe links are dropped", () => {
  expect(linkIdentifiers(`ratio 1.54 (${artifact}) \`${artifact}\``)).toContain(`[${artifact}](/artifact/${artifact})`);
  expect(linkIdentifiers(`\`${artifact}\``)).toBe(`\`${artifact}\``);
  render(<MemoryRouter><Markdown source={`See ${artifact}. <script>alert(1)</script> [x](javascript:alert(1))`} /></MemoryRouter>);
  expect(screen.getByRole("link", { name: artifact }).getAttribute("href")).toBe(`/artifact/${artifact}`);
  expect(document.querySelector("script")).toBeNull();
  expect(screen.queryByRole("link", { name: "x" })).toBeNull();
});
