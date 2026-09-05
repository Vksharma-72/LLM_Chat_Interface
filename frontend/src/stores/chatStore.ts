import { create } from "zustand";
import { api, getErrorMessage } from "../services/api";
import { streamChat } from "../services/chat";
import type { StreamEvent } from "../services/chat";
import type { Attachment, Conversation, Message, StreamError, Usage } from "../types/chat";

export interface SendParams {
  model?: string | null;
  temperature?: number;
  maxTokens?: number;
  systemPrompt?: string | null;
}



/** Pure reducer for SSE events — unit-tested in isolation (§9). */
export interface StreamAccumulator {
  conversationId: string | null;
  userMessage: Message | null;
  content: string;
  assistantMessage: Message | null;
  usage: Usage | null;
  error: StreamError | null;
}

export function applyStreamEvent(
  acc: StreamAccumulator,
  event: StreamEvent
): StreamAccumulator {
  switch (event.type) {
    case "meta":
      return { ...acc, conversationId: event.conversationId, userMessage: event.userMessage };
    case "delta":
      return { ...acc, content: acc.content + event.content };
    case "done":
      return { ...acc, assistantMessage: event.assistantMessage, usage: event.usage };
    case "error":
      return { ...acc, error: { code: event.code, message: event.message } };
  }
}

interface ChatState {
  conversations: Conversation[];
  total: number;
  query: string;
  currentId: string | null;
  messages: Message[];
  isStreaming: boolean;
  streamingContent: string;
  error: string | null;
  errorCode: string | null;
  isLoadingConversation: boolean;
  isLoadingList: boolean;
  loadConversations: (q?: string) => Promise<void>;
  openConversation: (id: string) => Promise<void>;
  newConversation: () => void;
  send: (content: string, params?: SendParams, attachments?: Attachment[]) => Promise<void>;
  regenerate: (params?: SendParams) => Promise<void>;
  abort: () => void;
  deleteConversation: (id: string) => Promise<void>;
  togglePin: (id: string) => Promise<void>;
  clearCurrent: () => Promise<void>;
}

let abortController: AbortController | null = null;
let tempCounter = 0;

export const useChatStore = create<ChatState>()((set, get) => ({
  conversations: [],
  total: 0,
  query: "",
  currentId: null,
  messages: [],
  isStreaming: false,
  streamingContent: "",
  error: null,
  errorCode: null,
  isLoadingConversation: false,
  isLoadingList: false,

  loadConversations: async (q?: string) => {
    const query = q ?? get().query;
    set({ query, isLoadingList: true });
    try {
      const response = await api.get<{ items: Conversation[]; total: number }>(
        "/conversations",
        { params: query ? { q: query } : undefined }
      );
      set({ conversations: response.data.items, total: response.data.total });
    } finally {
      set({ isLoadingList: false });
    }
  },

  openConversation: async (id) => {
    set({ isLoadingConversation: true });
    try {
      const response = await api.get<{ conversation: Conversation; messages: Message[] }>(
        `/conversations/${id}`
      );
      set({ currentId: id, messages: response.data.messages, error: null });
    } finally {
      set({ isLoadingConversation: false });
    }
  },

  newConversation: () => set({ currentId: null, messages: [], error: null }),

  send: async (content, params = {}, attachments: Attachment[] = []) => {
    const state = get();
    if (state.isStreaming) {
      return;
    }
    abortController = new AbortController();
    set({ isStreaming: true, streamingContent: "", error: null });

    const tempId = `temp-${++tempCounter}`;
    const optimistic: Message = {
      id: tempId,
      conversation_id: state.currentId ?? "",
      role: "user",
      content,
      tokens: null,
      metadata: {},
      attachments,
      created_at: new Date().toISOString(),
    };
    set({ messages: [...state.messages, optimistic] });

    let acc: StreamAccumulator = {
      conversationId: state.currentId,
      userMessage: null,
      content: "",
      assistantMessage: null,
      usage: null,
      error: null,
    };
    try {
      await streamChat(
        {
          conversation_id: state.currentId,
          content,
          attachment_ids: attachments.map((attachment) => attachment.id),
          model: params.model ?? null,
          temperature: params.temperature,
          max_tokens: params.maxTokens,
          system_prompt: params.systemPrompt ?? null,
        },
        (event) => {
          acc = applyStreamEvent(acc, event);
          if (event.type === "meta") {
            set((s) => ({
              currentId: event.conversationId,
              messages: s.messages.map((m) =>
                m.id === event.userMessage.id || m.id === tempId ? event.userMessage : m
              ),
            }));
            void get().loadConversations();
          } else if (event.type === "delta") {
            set({ streamingContent: acc.content });
          } else if (event.type === "done") {
            set((s) => ({
              messages: [...s.messages, event.assistantMessage],
              streamingContent: "",
            }));
            void get().loadConversations();
          } else if (event.type === "error") {
            set({ error: event.message, errorCode: event.code });
          }
        },
        abortController.signal
      );
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        set({ error: getErrorMessage(err), errorCode: null });
      }
    } finally {
      set({ isStreaming: false, streamingContent: "" });
      abortController = null;
    }
  },

  regenerate: async (params = {}) => {
    const { currentId, messages, isStreaming } = get();
    if (isStreaming || !currentId) {
      return;
    }
    const last = messages[messages.length - 1];
    if (!last || last.role !== "assistant") {
      return;
    }
    abortController = new AbortController();
    set({
      isStreaming: true,
      streamingContent: "",
      error: null,
      messages: messages.slice(0, -1),
    });

    let acc: StreamAccumulator = {
      conversationId: currentId,
      userMessage: null,
      content: "",
      assistantMessage: null,
      usage: null,
      error: null,
    };
    try {
      await streamChat(
        {
          conversation_id: currentId,
          regenerate: true,
          model: params.model ?? null,
          temperature: params.temperature,
          max_tokens: params.maxTokens,
          system_prompt: params.systemPrompt ?? null,
        },
        (event) => {
          acc = applyStreamEvent(acc, event);
          if (event.type === "delta") {
            set({ streamingContent: acc.content });
          } else if (event.type === "done") {
            set((s) => ({
              messages: [...s.messages, event.assistantMessage],
              streamingContent: "",
            }));
            void get().loadConversations();
          } else if (event.type === "error") {
            set({ error: event.message, errorCode: event.code });
          }
        },
        abortController.signal
      );
    } catch (err) {
      if ((err as Error)?.name !== "AbortError") {
        set({ error: getErrorMessage(err), errorCode: null });
      }
    } finally {
      set({ isStreaming: false, streamingContent: "" });
      abortController = null;
    }
  },

  abort: () => {
    abortController?.abort();
  },

  deleteConversation: async (id) => {
    await api.delete(`/conversations/${id}`);
    set((s) => ({
      conversations: s.conversations.filter((c) => c.id !== id),
      total: Math.max(0, s.total - 1),
      currentId: s.currentId === id ? null : s.currentId,
      messages: s.currentId === id ? [] : s.messages,
    }));
  },

  togglePin: async (id) => {
    const item = get().conversations.find((c) => c.id === id);
    if (!item) {
      return;
    }
    await api.patch(`/conversations/${id}`, { is_pinned: !item.is_pinned });
    await get().loadConversations();
  },

  clearCurrent: async () => {
    const { currentId } = get();
    if (!currentId) {
      return;
    }
    await api.delete(`/conversations/${currentId}`);
    const created = await api.post<Conversation>("/conversations", {});
    set({ currentId: created.data.id, messages: [] });
    await get().loadConversations();
  },
}));
