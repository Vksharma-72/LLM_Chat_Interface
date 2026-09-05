export interface UsageDay {
  date: string;
  tokens: number;
  requests: number;
}

export interface UsageResponse {
  days: UsageDay[];
}
