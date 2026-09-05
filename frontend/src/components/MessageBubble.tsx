import { useEffect, useState } from "react";
import { format } from "date-fns";
import MarkdownContent from "./MarkdownContent";
import Lightbox from "./Lightbox";
import { api } from "../services/api";
import type { Attachment, Message } from "../types/chat";

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Fetches blob URLs for the given attachment ids (private, Bearer-authenticated). */
function useAttachmentUrls(ids: string[]): {
  urls: Record<string, string>;
  failed: Record<string, boolean>;
} {
  const [urls, setUrls] = useState<Record<string, string>>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const key = ids.join(",");

  useEffect(() => {
    if (!ids.length) {
      return;
    }
    let cancelled = false;
    const created: string[] = [];
    (async () => {
      await Promise.all(
        ids.map(async (id) => {
          try {
            const response = await api.get(`/attachments/${id}/content`, {
              responseType: "blob",
            });
            const objectUrl = URL.createObjectURL(response.data as Blob);
            created.push(objectUrl);
            if (!cancelled) {
              setUrls((current) => ({ ...current, [id]: objectUrl }));
            }
          } catch {
            if (!cancelled) {
              setFailed((current) => ({ ...current, [id]: true }));
            }
          }
        })
      );
    })();
    return () => {
      cancelled = true;
      created.forEach((objectUrl) => URL.revokeObjectURL(objectUrl));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { urls, failed };
}

function AttachmentDownload({ attachment }: { attachment: Attachment }) {
  const [busy, setBusy] = useState(false);

  const handleDownload = async () => {
    setBusy(true);
    try {
      const response = await api.get(`/attachments/${attachment.id}/content`, {
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = attachment.filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={handleDownload}
      disabled={busy}
      className="flex items-center gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-left text-xs text-gray-800 hover:bg-gray-50 disabled:opacity-60 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
    >
      <span aria-hidden="true">📄</span>
      <span className="max-w-48 truncate">{attachment.filename}</span>
      <span className="text-gray-400">{formatSize(attachment.size_bytes)}</span>
      <span aria-hidden="true" className="text-indigo-500">
        ⬇
      </span>
    </button>
  );
}

function MessageAttachments({ attachments }: { attachments: Attachment[] }) {
  const { urls, failed } = useAttachmentUrls(attachments.map((attachment) => attachment.id));
  const [lightboxIndex, setLightboxIndex] = useState<number | null>(null);

  const images = attachments.filter((attachment) => attachment.kind === "image");
  const lightboxImages = images.map((attachment) => ({
    id: attachment.id,
    url: urls[attachment.id] ?? "",
    filename: attachment.filename,
  }));

  return (
    <div className="space-y-2">
      {images.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {images.map((attachment, index) => {
            if (failed[attachment.id]) {
              return (
                <span key={attachment.id} className="text-xs text-red-400">
                  Could not load {attachment.filename}
                </span>
              );
            }
            return urls[attachment.id] ? (
              <button
                key={attachment.id}
                type="button"
                onClick={() => setLightboxIndex(index)}
                aria-label={`View ${attachment.filename}`}
              >
                <img
                  src={urls[attachment.id]}
                  alt={attachment.filename}
                  className="max-h-64 rounded-lg border border-gray-200 object-cover dark:border-gray-700"
                />
              </button>
            ) : (
              <div
                key={attachment.id}
                className="h-32 w-48 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-800"
              />
            );
          })}
        </div>
      )}
      {attachments
        .filter((attachment) => attachment.kind === "video")
        .map((attachment) =>
          urls[attachment.id] ? (
            <video key={attachment.id} src={urls[attachment.id]} controls className="max-h-72 rounded-lg" />
          ) : (
            <div key={attachment.id} className="h-20 w-64 animate-pulse rounded-lg bg-gray-200 dark:bg-gray-800" />
          )
        )}
      {attachments
        .filter((attachment) => attachment.kind === "audio")
        .map((attachment) =>
          urls[attachment.id] ? (
            <audio key={attachment.id} src={urls[attachment.id]} controls className="w-64" />
          ) : (
            <div key={attachment.id} className="h-8 w-64 animate-pulse rounded bg-gray-200 dark:bg-gray-800" />
          )
        )}
      {attachments
        .filter((attachment) => attachment.kind === "document" || attachment.kind === "other")
        .map((attachment) => <AttachmentDownload key={attachment.id} attachment={attachment} />)}
      {lightboxIndex !== null && lightboxImages[lightboxIndex]?.url && (
        <Lightbox
          images={lightboxImages}
          index={lightboxIndex}
          onClose={() => setLightboxIndex(null)}
          onNavigate={setLightboxIndex}
        />
      )}
    </div>
  );
}

export default function MessageBubble({
  message,
  showRegenerate,
  onRegenerate,
}: {
  message: Message;
  showRegenerate: boolean;
  onRegenerate: () => void;
}) {
  const isUser = message.role === "user";
  const [copied, setCopied] = useState(false);
  const attachments = message.attachments ?? [];

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] md:max-w-[75%] ${isUser ? "items-end" : "items-start"}`}>
        {attachments.length > 0 && <MessageAttachments attachments={attachments} />}
        {(message.content || attachments.length === 0) && (
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
        )}
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
