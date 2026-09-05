import { useAuthStore } from "../stores/authStore";
import type { Message, Usage } from "../types/chat";

export interface ChatStreamRequestBody {
  conversation_id?: string | null;
  content?: string;
  regenerate?: boolean;
  temperature?: number;
  max_tokens?: number;
  model?: string | null;
  system_prompt?: string | null;
}

export type StreamEvent =
  | { type: "meta"; conversationId: string; userMessage: Message }
  | { type: "delta"; content: string }
  | { type: "done"; assistantMessage: Message; usage: Usage | null }
  | { type: "error"; code: string; message: string };

function toStreamEvent(name: string, data: Record<string, unknown>): StreamEvent {
  switch (name) {
    case "meta":
      return {
        type: "meta",
        conversationId: String(data.conversation_id),
        userMessage: data.user_message as Message,
      };
    case "delta":
      return { type: "delta", content: String(data.content ?? "") };
    case "done":
      return {
        type: "done",
        assistantMessage: data.assistant_message as Message,
        usage: (data.usage as Usage | null) ?? null,
      };
    case "error": {
      const error = data.error as { code?: string; message?: string };
      return {
        type: "error",
        code: error?.code ?? "unknown",
        message: error?.message ?? "Unknown streaming error",
      };
    }
    default:
      throw new Error(`Unknown SSE event: ${name}`);
  }
}

/**
 * Consumes POST /api/chat/stream (§7: meta → delta* → done → error) via a
 * fetch ReadableStream. Retries once after a successful token refresh on 401.
 */
export async function streamChat(
  body: ChatStreamRequestBody,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal
): Promise<void> {
  const doFetch = (token: string | null) =>
    fetch("/api/chat/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
      signal,
    });

  let response = await doFetch(useAuthStore.getState().accessToken);
  if (response.status === 401) {
    const newToken = await useAuthStore.getState().refresh();
    if (newToken) {
      response = await doFetch(newToken);
    }
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const data = (await response.json()) as { error?: { message?: string } };
      message = data.error?.message ?? message;
    } catch {
      // not a JSON error envelope — keep the generic message
    }
    throw new Error(message);
  }
  if (!response.body) {
    throw new Error("Streaming is not supported by this browser");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent: string | null = null;
  let dataLines: string[] = [];

  const dispatch = () => {
    if (currentEvent && dataLines.length > 0) {
      const data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
      onEvent(toStreamEvent(currentEvent, data));
    }
    currentEvent = null;
    dataLines = [];
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) {
      if (line === "") {
        dispatch();
      } else if (line.startsWith("event:")) {
        currentEvent = line.slice("event:".length).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice("data:".length).trim());
      }
      // comments/heartbeats (lines starting with ":") are ignored
    }
  }
  dispatch();
}
