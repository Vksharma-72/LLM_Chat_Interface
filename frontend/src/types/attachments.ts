export interface Attachment {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  kind: "image" | "video" | "audio" | "document" | "other";
  url: string;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
}
