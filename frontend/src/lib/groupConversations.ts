import { addDays, startOfDay } from "date-fns";
import type { Conversation } from "../types/chat";

export interface ConversationGroup {
  label: string;
  items: Conversation[];
}

/** Pinned first, then Today / Yesterday / Earlier by updated_at (§7). */
export function groupConversations(items: Conversation[]): ConversationGroup[] {
  const groups: ConversationGroup[] = [];
  const pinned = items.filter((item) => item.is_pinned);
  if (pinned.length > 0) {
    groups.push({ label: "Pinned", items: pinned });
  }

  const today = startOfDay(new Date());
  const yesterday = addDays(today, -1);
  const buckets: Record<string, Conversation[]> = {
    Today: [],
    Yesterday: [],
    Earlier: [],
  };
  for (const item of items) {
    if (item.is_pinned) {
      continue;
    }
    const day = startOfDay(new Date(item.updated_at)).getTime();
    if (day >= today.getTime()) {
      buckets.Today.push(item);
    } else if (day >= yesterday.getTime()) {
      buckets.Yesterday.push(item);
    } else {
      buckets.Earlier.push(item);
    }
  }
  for (const [label, bucketItems] of Object.entries(buckets)) {
    if (bucketItems.length > 0) {
      groups.push({ label, items: bucketItems });
    }
  }
  return groups;
}
