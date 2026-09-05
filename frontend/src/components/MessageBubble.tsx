import { useState } from "react";
import { format } from "date-fns";
import MarkdownContent from "./MarkdownContent";
import type { Message } from "../types/chat";

interface MessageBubbleProps {
  message: Message;
  showRegenerate: boolean;
  onRegenerate: () => void;
}

export default function MessageBubble({
  message,
  showRegenerate,
  onRegenerate,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] md:max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm ${
            isUser
              ? "rounded-br-md bg-indigo-600 text-white"
              : "rounded-bl-md border border-gray-200 bg-white text-gray-900 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : (
            <MarkdownContent content={message.content} />
          )}
        </div>
        <div
          className={`mt-1 flex items-center gap-2 px-2 text-xs text-gray-400 dark:text-gray-500 ${isUser ? "justify-end" : ""}`}
        >
          <time dateTime={message.created_at}>
            {format(new Date(message.created_at), "HH:mm")}
          </time>
          <button
            type="button"
            onClick={handleCopy}
            aria-label="Copy message"
            className="hover:text-gray-600 dark:hover:text-gray-300"
          >
            {copied ? "Copied!" : "Copy"}
          </button>
          {showRegenerate && (
            <button
              type="button"
              onClick={onRegenerate}
              aria-label="Regenerate reply"
              className="hover:text-gray-600 dark:hover:text-gray-300"
            >
              ↻ Regenerate
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
