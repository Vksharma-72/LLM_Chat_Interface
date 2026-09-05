import { useEffect, useState } from "react";
import { useChatStore } from "../stores/chatStore";
import { useDebounce } from "../hooks/useDebounce";
import { useToast } from "./Toast";
import { groupConversations } from "../lib/groupConversations";
import type { Conversation } from "../types/chat";

interface SidebarProps {
  onDelete: (id: string) => void;
}

export default function Sidebar({ onDelete }: SidebarProps) {
  const conversations = useChatStore((state) => state.conversations);
  const currentId = useChatStore((state) => state.currentId);
  const newConversation = useChatStore((state) => state.newConversation);
  const openConversation = useChatStore((state) => state.openConversation);
  const togglePin = useChatStore((state) => state.togglePin);
  const loadConversations = useChatStore((state) => state.loadConversations);
  const isLoadingList = useChatStore((state) => state.isLoadingList);
  const { push } = useToast();

  const [search, setSearch] = useState("");
  const debouncedSearch = useDebounce(search, 300);

  useEffect(() => {
    void loadConversations(debouncedSearch.trim() || undefined);
  }, [debouncedSearch, loadConversations]);

  const groups = groupConversations(conversations);

  const handleTogglePin = async (conversation: Conversation) => {
    await togglePin(conversation.id);
    push(
      conversation.is_pinned ? "Conversation unpinned" : "Conversation pinned",
      "info"
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-2 p-3">
        <button
          type="button"
          onClick={newConversation}
          className="w-full rounded-md bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600"
        >
          New chat
        </button>
        <input
          id="conversation-search"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search conversations… (Ctrl+K)"
          aria-label="Search conversations"
          className="w-full rounded-md border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        />
      </div>

      <nav className="flex-1 overflow-y-auto px-2 pb-3" aria-label="Conversations">
        {isLoadingList && conversations.length === 0 ? (
          <div className="space-y-2 px-1" aria-hidden="true">
            {[0, 1, 2].map((index) => (
              <div
                key={index}
                className="h-9 animate-pulse rounded-md bg-gray-200 dark:bg-gray-800"
              />
            ))}
          </div>
        ) : groups.length === 0 ? (
          <p className="px-3 py-6 text-center text-sm text-gray-500 dark:text-gray-400">
            {debouncedSearch.trim()
              ? "No conversations match your search."
              : "No conversations yet."}
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.label} className="mb-3">
              <h3 className="px-3 py-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                {group.label}
              </h3>
              <ul>
                {group.items.map((conversation) => (
                  <ConversationItem
                    key={conversation.id}
                    conversation={conversation}
                    active={conversation.id === currentId}
                    onOpen={() => void openConversation(conversation.id)}
                    onTogglePin={() => void handleTogglePin(conversation)}
                    onDelete={() => onDelete(conversation.id)}
                  />
                ))}
              </ul>
            </div>
          ))
        )}
      </nav>
    </div>
  );
}

interface ConversationItemProps {
  conversation: Conversation;
  active: boolean;
  onOpen: () => void;
  onTogglePin: () => void;
  onDelete: () => void;
}

function ConversationItem({
  conversation,
  active,
  onOpen,
  onTogglePin,
  onDelete,
}: ConversationItemProps) {
  return (
    <li
      data-testid="conversation-item"
      className={`group relative flex items-center rounded-md ${active ? "bg-indigo-50 dark:bg-indigo-950" : "hover:bg-gray-100 dark:hover:bg-gray-800"}`}
    >
      <button
        type="button"
        onClick={onOpen}
        className="min-w-0 flex-1 px-3 py-2 text-left text-sm text-gray-900 dark:text-gray-100"
      >
        <span className="block truncate">
          {conversation.is_pinned ? "📌 " : ""}
          {conversation.title}
        </span>
      </button>
      <span className="mr-2 hidden shrink-0 gap-1 group-hover:flex">
        <button
          type="button"
          onClick={onTogglePin}
          aria-label={conversation.is_pinned ? "Unpin conversation" : "Pin conversation"}
          className="rounded p-1 text-gray-500 hover:bg-gray-200 dark:text-gray-400 dark:hover:bg-gray-700"
        >
          📌
        </button>
        <button
          type="button"
          onClick={onDelete}
          aria-label="Delete conversation"
          className="rounded p-1 text-gray-500 hover:bg-gray-200 dark:text-gray-400 dark:hover:bg-gray-700"
        >
          🗑️
        </button>
      </span>
      {active && <span className="absolute inset-y-1 left-0 w-1 rounded bg-indigo-500" />}
    </li>
  );
}
