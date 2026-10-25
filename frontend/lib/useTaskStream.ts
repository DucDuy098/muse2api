"use client";

import { useEffect, useState } from "react";
import { api } from "./api";

interface StreamEvent {
  status?: string;
  progress?: number;
  error?: string | null;
  url?: string | null;
  ping?: boolean;
}

/** Subscribes to GET /admin/tasks/{id}/stream (SSE) while the task is live;
 * closes itself once status is completed/failed. */
export function useTaskStream(taskId: string | null) {
  const [event, setEvent] = useState<StreamEvent | null>(null);

  useEffect(() => {
    if (!taskId) return;
    setEvent(null);
    const es = new EventSource(api.base + `/admin/tasks/${taskId}/stream`, { withCredentials: true });
    es.onmessage = (msg) => {
      const data: StreamEvent = JSON.parse(msg.data);
      if (data.ping) return;
      setEvent(data);
      if (data.status === "completed" || data.status === "failed") es.close();
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [taskId]);

  return event;
}
