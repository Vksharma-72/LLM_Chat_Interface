import { describe, expect, it } from "vitest";
import { groupConversations } from "../lib/groupConversations";
import type { Conversation } from "../types/chat";

function conversation(partial: Partial<Conversation>): Conversation {
  return {
    id: partial.id ?? Math.random().toString(36).slice(2),
    title: partial.title ?? "Conversation",
    is_pinned: partial.is_pinned ?? false,
    model: null,
    message_count: 0,
    created_at: partial.created_at ?? "2026-09-06T10:00:00Z",
    updated_at: partial.updated_at ?? "2026-09-06T10:00:00Z",
  };
}

describe("groupConversations", () => {
  it("puts pinned conversations in their own first group", () => {
    const groups = groupConversations([
      conversation({ id: "a", updated_at: new Date().toISOString() }),
      conversation({ id: "b", is_pinned: true, updated_at: "2020-01-01T00:00:00Z" }),
    ]);
    expect(groups[0].label).toBe("Pinned");
    expect(groups[0].items.map((item) => item.id)).toEqual(["b"]);
  });

  it("buckets unpinned conversations into Today / Yesterday / Earlier", () => {
    const now = new Date();
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const groups = groupConversations([
      conversation({ id: "today-1", updated_at: now.toISOString() }),
      conversation({ id: "yesterday-1", updated_at: yesterday.toISOString() }),
      conversation({ id: "earlier-1", updated_at: "2020-01-01T00:00:00Z" }),
    ]);

    expect(groups.map((group) => group.label)).toEqual(["Today", "Yesterday", "Earlier"]);
    expect(groups[0].items.map((item) => item.id)).toEqual(["today-1"]);
    expect(groups[1].items.map((item) => item.id)).toEqual(["yesterday-1"]);
    expect(groups[2].items.map((item) => item.id)).toEqual(["earlier-1"]);
  });

  it("omits empty groups", () => {
    const groups = groupConversations([
      conversation({ id: "only", updated_at: new Date().toISOString() }),
    ]);
    expect(groups.length).toBe(1);
    expect(groups[0].label).toBe("Today");
  });
});
