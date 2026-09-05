import { describe, expect, it } from "vitest";
import { friendlyError } from "../lib/friendlyError";

describe("friendlyError", () => {
  it("maps llm_unavailable to a model-unavailable banner", () => {
    expect(friendlyError("llm_unavailable", "raw")).toContain("model is currently unavailable");
  });

  it("maps llm_rate_limited and rate_limited to slow-down banners", () => {
    expect(friendlyError("llm_rate_limited", "raw")).toContain("slow down");
    expect(friendlyError("rate_limited", "raw")).toContain("Slow down");
  });

  it("passes unknown codes through with the original message", () => {
    expect(friendlyError(null, "Something broke")).toBe("Something broke");
    expect(friendlyError("not_found", "Conversation not found")).toBe("Conversation not found");
  });
});
