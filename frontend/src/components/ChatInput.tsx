import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import type { PendingUpload } from "../hooks/useAttachmentUpload";

const MAX_MESSAGE_CHARS = 16000;

interface ChatInputProps {
  disabled: boolean;
  isStreaming: boolean;
  pending: PendingUpload[];
  addFiles: (files: FileList | File[]) => void;
  removePending: (id: string) => void;
  onSend: (content: string, attachmentIds: string[]) => void;
  onStop: () => void;
}

export default function ChatInput({
  disabled,
  isStreaming,
  pending,
  addFiles,
  removePending,
  onSend,
  onStop,
}: ChatInputProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Auto-grow up to a cap, then scroll internally (§7).
  useEffect(() => {
    const element = textareaRef.current;
    if (!element) {
      return;
    }
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, 200)}px`;
  }, [value]);

  const uploading = pending.some((entry) => !entry.attachment);
  const attachmentIds = pending
    .map((entry) => entry.attachment?.id)
    .filter((id): id is string => Boolean(id));

  const submit = () => {
    const trimmed = value.trim();
    if (isStreaming || uploading) {
      return;
    }
    if (!trimmed && attachmentIds.length === 0) {
      return;
    }
    if (trimmed.length > MAX_MESSAGE_CHARS) {
      return;
    }
    onSend(trimmed, attachmentIds);
    setValue("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  const handlePaste = (event: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const files = Array.from(event.clipboardData.files);
    if (files.length > 0) {
      event.preventDefault();
      void addFiles(files);
    }
  };

  return (
    <div className="border-t border-gray-200 px-3 py-3 sm:px-4 dark:border-gray-800">
      {pending.length > 0 && (
        <div className="mx-auto mb-2 flex max-w-3xl flex-wrap gap-2">
          {pending.map((entry) => (
            <div
              key={entry.id}
              data-testid="pending-attachment"
              className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-2 py-1 text-xs text-gray-700 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
            >
              <span aria-hidden="true">📎</span>
              <span className="max-w-40 truncate">{entry.file.name}</span>
              {entry.attachment ? (
                <span className="text-green-600 dark:text-green-400">✓</span>
              ) : (
                <span className="text-gray-400">{entry.progress}%</span>
              )}
              <button
                type="button"
                onClick={() => removePending(entry.id)}
                aria-label={`Remove ${entry.file.name}`}
                className="text-gray-400 hover:text-red-500"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="mx-auto flex max-w-3xl items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept="image/*,video/*,audio/*,.pdf,.docx,.txt,.md,.csv,.json"
          className="hidden"
          onChange={(event) => {
            if (event.target.files) {
              void addFiles(event.target.files);
            }
            event.target.value = "";
          }}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          aria-label="Attach files"
          className="mb-6 rounded-lg border border-gray-300 px-2.5 py-2 text-sm text-gray-600 hover:bg-gray-100 disabled:opacity-60 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
        >
          📎
        </button>
        <div className="flex-1">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            disabled={disabled}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            placeholder="Send a message… (Enter to send, Shift+Enter for a new line)"
            aria-label="Message"
            className="w-full resize-none rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          />
          <div className="mt-1 text-right text-xs text-gray-400 dark:text-gray-500">
            <span className={value.length > MAX_MESSAGE_CHARS - 1000 ? "text-red-500" : undefined}>
              {value.length}
            </span>
            /{MAX_MESSAGE_CHARS}
          </div>
        </div>
        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            className="mb-6 rounded-lg border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
          >
            Stop
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={disabled || uploading || (!value.trim() && attachmentIds.length === 0)}
            className="mb-6 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-indigo-500 dark:hover:bg-indigo-600"
          >
            Send
          </button>
        )}
      </div>
    </div>
  );
}
