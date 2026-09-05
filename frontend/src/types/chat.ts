export interface Conversation {
  id: string;
  title: string;
  is_pinned: boolean;
  model: string | null;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export type MessageRole = "user" | "assistant" | "system";

export interface Message {
  id: string;
  conversation_id: string;
  role: MessageRole;
  content: string;
  tokens: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Usage {
  prompt_tokens: number;
  completion_tokens: number;
}

export interface StreamError {
  code: string;
  message: string;
}

export interface ConversationDetail {
  conversation: Conversation;
  messages: Message[];
}
