import { useCallback, useState } from "react";
import { api, getErrorMessage } from "../services/api";
import { useToast } from "../components/Toast";
import type { Attachment } from "../types/attachments";

const MAX_FILE_BYTES = 100 * 1024 * 1024;

export interface PendingUpload {
  id: string;
  file: File;
  progress: number;
  attachment?: Attachment;
}

/** Upload queue for the composer: pre-checks size, tracks progress, surfaces errors. */
export function useAttachmentUpload() {
  const { push } = useToast();
  const [pending, setPending] = useState<PendingUpload[]>([]);

  const removePending = useCallback((id: string) => {
    setPending((current) => current.filter((entry) => entry.id !== id));
  }, []);

  const reset = useCallback(() => setPending([]), []);

  const addFiles = useCallback(
    async (files: FileList | File[]) => {
      for (const file of Array.from(files)) {
        if (file.size > MAX_FILE_BYTES) {
          push("That file is too large — the limit is 100 MB per file.", "error");
          continue;
        }
        const entryId = crypto.randomUUID();
        setPending((current) => [...current, { id: entryId, file, progress: 0 }]);
        try {
          const formData = new FormData();
          formData.append("file", file);
          const response = await api.post<Attachment>("/attachments", formData, {
            onUploadProgress: (event) => {
              const percent = event.total ? Math.round((event.loaded / event.total) * 100) : 0;
              setPending((current) =>
                current.map((entry) =>
                  entry.id === entryId ? { ...entry, progress: percent } : entry
                )
              );
            },
          });
          setPending((current) =>
            current.map((entry) =>
              entry.id === entryId
                ? { ...entry, attachment: response.data, progress: 100 }
                : entry
            )
          );
        } catch (err) {
          removePending(entryId);
          push(getErrorMessage(err), "error");
        }
      }
    },
    [push, removePending]
  );

  return { pending, addFiles, removePending, reset };
}
