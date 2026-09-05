import { render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import MarkdownContent from "../components/MarkdownContent";
import { useAttachmentUpload } from "../hooks/useAttachmentUpload";
import { applyStreamEvent, type StreamAccumulator } from "../stores/chatStore";
import type { Attachment, Message } from "../types/chat";

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return { ...actual, api: { ...actual.api, post } };
});

const userMessage: Message = {
  id: "m-user",
  conversation_id: "c-1",
  role: "user",
  content: "hello",
  tokens: null,
  metadata: {},
  attachments: [
    {
      id: "a-1",
      filename: "cat.png",
      mime_type: "image/png",
      size_bytes: 156,
      kind: "image",
      url: "/api/attachments/a-1/content",
    },
  ],
  created_at: "2026-09-06T10:00:00Z",
};

const assistantMessage: Message = {
  id: "m-bot",
  conversation_id: "c-1",
  role: "assistant",
  content: "hi there",
  tokens: 3,
  metadata: { model: "test-model" },
  attachments: [],
  created_at: "2026-09-06T10:00:01Z",
};

function initial(): StreamAccumulator {
  return {
    conversationId: null,
    userMessage: null,
    content: "",
    assistantMessage: null,
    usage: null,
    error: null,
  };
}

describe("streaming reducer with attachments", () => {
  it("meta replaces the optimistic temp message including its attachments", () => {
    const acc = applyStreamEvent(initial(), {
      type: "meta",
      conversationId: "c-1",
      userMessage,
    });
    expect(acc.userMessage?.attachments[0]?.filename).toBe("cat.png");
  });

  it("done stores the assistant message (no attachments) and usage", () => {
    let acc = applyStreamEvent(initial(), { type: "delta", content: "hi" });
    acc = applyStreamEvent(acc, {
      type: "done",
      assistantMessage,
      usage: { prompt_tokens: 4, completion_tokens: 3 },
    });
    expect(acc.assistantMessage?.attachments).toEqual([]);
    expect(acc.usage).toEqual({ prompt_tokens: 4, completion_tokens: 3 });
  });
});

describe("useAttachmentUpload", () => {
  beforeEach(() => {
    post.mockReset();
  });

  it("rejects oversized files without an upload request", async () => {
    const { result } = renderHook(() => useAttachmentUpload());
    const bigFile = new File([new Uint8Array(101 * 1024 * 1024)], "big.bin");

    await result.current.addFiles([bigFile]);

    expect(post).not.toHaveBeenCalled();
    expect(result.current.pending).toHaveLength(0);
  });

  it("uploads a valid file and exposes the attachment", async () => {
    const attachment: Attachment = {
      id: "a-9",
      filename: "cat.png",
      mime_type: "image/png",
      size_bytes: 156,
      kind: "image",
      url: "/api/attachments/a-9/content",
    };
    post.mockResolvedValue({ data: attachment });

    const { result } = renderHook(() => useAttachmentUpload());
    const file = new File([new Uint8Array(10)], "cat.png", { type: "image/png" });

    await result.current.addFiles([file]);
    await waitFor(() => expect(result.current.pending[0]?.attachment).toEqual(attachment));
  });
});

describe("attachment rendering helpers", () => {
  it("renders exported markdown image syntax", () => {
    render(<MarkdownContent content={"![cat.png](/api/attachments/a-1/content)"} />);
    expect(screen.getByRole("img")).toHaveAttribute("alt", "cat.png");
  });
});
