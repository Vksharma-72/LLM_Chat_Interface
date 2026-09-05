import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MarkdownContent from "../components/MarkdownContent";

beforeEach(() => {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
    configurable: true,
  });
});

describe("MarkdownContent", () => {
  it("renders inline code without a copy button", () => {
    render(<MarkdownContent content={"Use `npm install` to start."} />);
    expect(screen.getByText("npm install")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy code" })).not.toBeInTheDocument();
  });

  it("renders a fenced code block with a working copy button", async () => {
    const code = "const answer = 42;\nconsole.log(answer);";
    render(<MarkdownContent content={"```js\n" + code + "\n```"} />);

    expect(screen.getByTestId("code-block")).toBeInTheDocument();
    expect(screen.getByText("js")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy code" }));
    await waitFor(() => {
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith(code);
    });
    expect(screen.getByText("Copied!")).toBeInTheDocument();
  });

  it("renders GFM tables", () => {
    const markdown = "| a | b |\n|---|---|\n| 1 | 2 |";
    render(<MarkdownContent content={markdown} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });
});
