import { useEffect, useState } from "react";
import { api } from "../services/api";

/**
 * Attachment URLs are private (Bearer-authenticated), so media is fetched as a
 * blob and rendered from an object URL instead of a plain <img src>.
 */
export function useAttachmentUrl(attachmentId: string | null): {
  url: string | null;
  error: boolean;
} {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!attachmentId) {
      return;
    }
    let objectUrl: string | null = null;
    let cancelled = false;
    api
      .get(`/attachments/${attachmentId}/content`, { responseType: "blob" })
      .then((response) => {
        if (cancelled) {
          return;
        }
        objectUrl = URL.createObjectURL(response.data as Blob);
        setUrl(objectUrl);
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [attachmentId]);

  return { url, error };
}
