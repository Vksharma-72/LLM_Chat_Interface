import { useCallback } from "react";
import { useChatStore } from "../stores/chatStore";
import type { SendParams } from "../stores/chatStore";
import { useUiStore } from "../stores/uiStore";

/**
 * Glue between the chat store and the persisted settings drawer values:
 * every send/regenerate carries the configured model/temperature/max
 * tokens/system prompt (§9).
 */
export function useChat() {
  const settings = useUiStore((state) => state.settings);

  const withSettings = useCallback(
    (): SendParams => ({
      model: settings.model || null,
      temperature: settings.temperature,
      maxTokens: settings.maxTokens,
      systemPrompt: settings.systemPrompt || null,
    }),
    [settings]
  );

  const send = useCallback(
    (content: string) => useChatStore.getState().send(content, withSettings()),
    [withSettings]
  );
  const regenerate = useCallback(
    () => useChatStore.getState().regenerate(withSettings()),
    [withSettings]
  );

  return {
    conversations: useChatStore((state) => state.conversations),
    total: useChatStore((state) => state.total),
    currentId: useChatStore((state) => state.currentId),
    messages: useChatStore((state) => state.messages),
    isStreaming: useChatStore((state) => state.isStreaming),
    streamingContent: useChatStore((state) => state.streamingContent),
    error: useChatStore((state) => state.error),
    errorCode: useChatStore((state) => state.errorCode),
    isLoadingConversation: useChatStore((state) => state.isLoadingConversation),
    isLoadingList: useChatStore((state) => state.isLoadingList),
    loadConversations: useChatStore((state) => state.loadConversations),
    openConversation: useChatStore((state) => state.openConversation),
    newConversation: useChatStore((state) => state.newConversation),
    abort: useChatStore((state) => state.abort),
    deleteConversation: useChatStore((state) => state.deleteConversation),
    togglePin: useChatStore((state) => state.togglePin),
    clearCurrent: useChatStore((state) => state.clearCurrent),
    send,
    regenerate,
  };
}
