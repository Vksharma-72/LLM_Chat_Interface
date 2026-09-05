import { describe, expect, it } from "vitest";
import { applyStreamEvent, type StreamAccumulator } from "../stores/chatStore";
import type { Message } from "../types/chat";

const userMessage: Message = {
  id: "m-user",
  conversation_id: "c-1",
  role: "user",
  content: "hello",
  tokens: null,
  metadata: {},
  created_at: "2026-09-06T10:00:00Z",
};

const assistantMessage: Message = {
  id: "m-bot",
  conversation_id: "c-1",
  role: "assistant",
  content: "hi there",
  tokens: 3,
  metadata: { model: "test-model" },
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

describe("applyStreamEvent (streaming reducer)", () => {
  it("meta sets the conversation id and persisted user message", () => {
    const acc = applyStreamEvent(initial(), {
      type: "meta",
      conversationId: "c-1",
      userMessage,
    });
    expect(acc.conversationId).toBe("c-1");
    expect(acc.userMessage).toEqual(userMessage);
    expect(acc.content).toBe("");
  });

  it("delta accumulates content in order", () => {
    let acc = applyStreamEvent(initial(), { type: "delta", content: "Hel" });
    acc = applyStreamEvent(acc, { type: "delta", content: "lo " });
    acc = applyStreamEvent(acc, { type: "delta", content: "world" });
    expect(acc.content).toBe("Hello world");
  });

  it("done stores the assistant message and usage, keeping the streamed text", () => {
    let acc = applyStreamEvent(initial(), { type: "delta", content: "hi there" });
    acc = applyStreamEvent(acc, {
      type: "done",
      assistantMessage,
      usage: { prompt_tokens: 4, completion_tokens: 3 },
    });
    expect(acc.assistantMessage).toEqual(assistantMessage);
    expect(acc.usage).toEqual({ prompt_tokens: 4, completion_tokens: 3 });
    expect(acc.content).toBe("hi there");
    expect(acc.error).toBeNull();
  });

  it("error records code and message without touching accumulated content", () => {
    let acc = applyStreamEvent(initial(), { type: "delta", content: "partial" });
    acc = applyStreamEvent(acc, {
      type: "error",
      code: "llm_unavailable",
      message: "The model is currently unavailable",
    });
    expect(acc.error).toEqual({
      code: "llm_unavailable",
      message: "The model is currently unavailable",
    });
    expect(acc.content).toBe("partial");
    expect(acc.assistantMessage).toBeNull();
  });
});
