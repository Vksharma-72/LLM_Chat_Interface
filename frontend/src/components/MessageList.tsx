import { useEffect, useRef } from "react";
import MarkdownContent from "./MarkdownContent";
import MessageBubble from "./MessageBubble";

interface MessageListProps {
  messages: import("../types/chat").Message[];
  isStreaming: boolean;
  streamingContent: string;
  isLoading: boolean;
  onRegenerate: () => void;
}

export default function MessageList({
  messages,
  isStreaming,
  streamingContent,
  isLoading,
  onRegenerate,
}: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isAtBottomRef = useRef(true);

  const handleScroll = () => {
    const element = containerRef.current;
    if (!element) {
      return;
    }
    const threshold = 48;
    isAtBottomRef.current =
      element.scrollHeight - element.scrollTop - element.clientHeight < threshold;
  };

  useEffect(() => {
    const element = containerRef.current;
    // Auto-scroll only when the user is already at the bottom (§7).
    if (element && isAtBottomRef.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [messages, streamingContent]);

  const lastAssistantId = isStreaming
    ? null
    : [...messages].reverse().find((message) => message.role === "assistant")?.id;

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="flex-1 space-y-4 overflow-y-auto px-4 py-6"
    >
      {isLoading && messages.length === 0 && (
        <div className="space-y-4" aria-hidden="true">
          {[80, 60, 70].map((widthPercent, index) => (
            <div
              key={index}
              className={`h-10 animate-pulse rounded-2xl bg-gray-200 dark:bg-gray-800 ${
                index % 2 === 0 ? "mr-auto" : "ml-auto"
              }`}
              style={{ width: `${widthPercent}%` }}
            />
          ))}
        </div>
      )}
      {messages.length === 0 && !isStreaming && !isLoading && (
        <div className="flex h-full items-center justify-center">
          <p className="text-center text-gray-500 dark:text-gray-400">
            Start a conversation — type a message below.
          </p>
        </div>
      )}
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          showRegenerate={message.id === lastAssistantId}
          onRegenerate={onRegenerate}
        />
      ))}
      {isStreaming && (
        <div className="flex justify-start">
          <div className="max-w-[85%] rounded-2xl rounded-bl-md border border-gray-200 bg-white px-4 py-2.5 text-sm dark:border-gray-800 dark:bg-gray-900">
            {streamingContent ? (
              <MarkdownContent content={streamingContent} />
            ) : (
              <span className="flex gap-1" aria-label="Assistant is typing">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:0ms]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:150ms]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 [animation-delay:300ms]" />
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
