"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import type { MediaItem } from "@/lib/types";

function fmtBytes(n: number): string {
  if (n < 1024 * 1024) return (n / 1024).toFixed(0) + " KB";
  return (n / 1024 / 1024).toFixed(1) + " MB";
}

export default function LibraryPage() {
  const [items, setItems] = useState<MediaItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get<{ media: MediaItem[] }>("/admin/media")
      .then((d) => setItems(d.media))
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Không tải được thư viện"))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Thư viện</h1>
      {loading ? (
        <p className="text-muted-foreground text-sm">Đang tải...</p>
      ) : items.length === 0 ? (
        <p className="text-muted-foreground text-sm">Chưa có ảnh/video nào.</p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
          {items.map((item) => (
            <div key={item.name} className="rounded border border-border overflow-hidden">
              {item.kind === "image" ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={api.base + item.url} alt={item.prompt ?? item.name} className="aspect-video object-cover w-full" />
              ) : (
                <video src={api.base + item.url} className="aspect-video object-cover w-full" muted />
              )}
              <div className="p-2 text-xs space-y-1">
                <div className="truncate text-muted-foreground" title={item.prompt}>{item.prompt || item.name}</div>
                <div className="flex justify-between text-muted-foreground">
                  <span>{item.account_label}</span>
                  <span>{fmtBytes(item.bytes)}</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
