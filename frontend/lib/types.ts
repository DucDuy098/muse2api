export interface Account {
  id: string;
  label: string;
  provider?: string;
  enabled: boolean;
  created_at: number;
  last_used: number | null;
  last_keepalive: number | null;
  use_count: number;
  ok: boolean | null;
  note: string;
  synced_at: number | null;
  checked_at?: number;
  expires_at: number | null;
  expires_estimated: boolean;
  cookie_count: number;
  essential_ok: boolean;
  quota?: {
    plan?: string;
    weekly_reset?: string;
    weekly_used_pct?: number;
    extra_left?: string;
    extra_used_pct?: number;
    extra_expires?: string;
    checked_at?: number;
  };
}

export interface AccountStats {
  total: number;
  enabled: number;
  disabled: number;
  healthy: number;
  error: number;
  expiring: number;
  expired: number;
}

export interface Task {
  id: string;
  object: string;
  kind: "image" | "video" | "chat";
  prompt: string;
  status: "queued" | "processing" | "completed" | "failed";
  progress?: number;
  created_at: number;
  updated_at: number;
  account?: string;
  account_label?: string;
  error?: string | null;
  result?: { filename?: string; url?: string; bytes?: number; kind?: string } | null;
  url?: string;
  elapsed?: number;
}

export interface MediaItem {
  name: string;
  url: string;
  bytes: number;
  mtime: number;
  kind: "image" | "video";
  prompt?: string;
  account_label?: string;
}

export interface BatchItem {
  index: number;
  prompt: string;
  status: "queued" | "submitting" | "running" | "completed" | "failed" | "cancelled" | "interrupted";
  task_id?: string | null;
  error?: string | null;
}

export interface Batch {
  id: string;
  created_at: number;
  kind: "image" | "video";
  size: string;
  duration: number;
  concurrency: number;
  items: BatchItem[];
  account_id: string | null;
  account_label: string;
  paused: boolean;
  pause_reason: string;
  reference_count: number;
}

export function fmtTime(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString("vi-VN");
}
