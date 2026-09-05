/** Human-friendly banner text for known API error codes (§8 polish). */
export function friendlyError(code: string | null, message: string): string {
  switch (code) {
    case "llm_unavailable":
      return "The model is currently unavailable. Please try again in a moment.";
    case "llm_rate_limited":
      return "The model is busy right now — slow down a little and try again.";
    case "rate_limited":
      return "You're doing that too often. Slow down and try again shortly.";
    default:
      return message;
  }
}
