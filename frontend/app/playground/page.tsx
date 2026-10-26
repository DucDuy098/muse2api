"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api, ApiError } from "@/lib/api";
import { useTaskStream } from "@/lib/useTaskStream";
import type { Account } from "@/lib/types";

const IMAGE_SIZES = ["1:1", "16:9", "9:16", "4:3", "3:4"];
const VIDEO_SIZES = ["16:9", "9:16", "1:1"];
const MAX_REFERENCE_IMAGES = 8;

function filesToDataUrls(files: FileList): Promise<string[]> {
  return Promise.all(
    Array.from(files).map(
      (file) =>
        new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve(reader.result as string);
          reader.onerror = reject;
          reader.readAsDataURL(file);
        })
    )
  );
}

export default function PlaygroundPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<string>("auto");
  const [kind, setKind] = useState<"image" | "video">("image");
  const [size, setSize] = useState("16:9");
  const [duration, setDuration] = useState(10);
  const [prompt, setPrompt] = useState("");
  const [referenceImages, setReferenceImages] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);

  useEffect(() => {
    api.get<{ accounts: Account[] }>("/admin/accounts").then((d) => setAccounts(d.accounts)).catch(() => {});
  }, []);

  const event = useTaskStream(taskId);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setSubmitting(true);
    setTaskId(null);
    try {
      const body: Record<string, unknown> = {
        prompt,
        size,
        account_id: accountId === "auto" ? null : accountId,
      };
      if (kind === "video") body.duration = duration;
      if (referenceImages.length === 1) body.reference_image = referenceImages[0];
      else if (referenceImages.length > 1) body.reference_images = referenceImages;
      const path = kind === "image" ? "/admin/generate/image" : "/admin/generate/video";
      const data = await api.post<{ id: string }>(path, body);
      setTaskId(data.id);
      setReferenceImages([]);
      toast.success("Đã gửi tác vụ " + data.id);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Gửi tác vụ thất bại");
    } finally {
      setSubmitting(false);
    }
  }

  const resultUrl = event?.url ? api.base + event.url : null;

  return (
    <div className="grid lg:grid-cols-2 gap-6 max-w-5xl">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dùng thử</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="flex gap-3">
              <div className="space-y-2 flex-1">
                <Label>Loại</Label>
                <Select value={kind} onValueChange={(v) => { setKind(v as "image" | "video"); setSize("16:9"); }}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="image">Tạo ảnh</SelectItem>
                    <SelectItem value="video">Tạo video</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 flex-1">
                <Label>Tỷ lệ</Label>
                <Select value={size} onValueChange={(v) => v && setSize(v)}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {(kind === "image" ? IMAGE_SIZES : VIDEO_SIZES).map((s) => (
                      <SelectItem key={s} value={s}>{s}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {kind === "video" && (
                <div className="space-y-2 w-28">
                  <Label>Giây</Label>
                  <Select value={String(duration)} onValueChange={(v) => v && setDuration(Number(v))}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {[5, 10].map((d) => <SelectItem key={d} value={String(d)}>{d}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
            <div className="space-y-2">
              <Label>Tài khoản tạo</Label>
              <Select value={accountId} onValueChange={(v) => v && setAccountId(v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="auto">Tự động chọn</SelectItem>
                  {accounts.filter((a) => a.enabled).map((a) => (
                    <SelectItem key={a.id} value={a.id}>{a.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Mô tả</Label>
              <Textarea rows={6} value={prompt} onChange={(e) => setPrompt(e.target.value)}
                placeholder="Mô tả ảnh/video cần tạo..." />
            </div>
            <div className="space-y-2">
              <Label>Ảnh tham khảo (tùy chọn, tối đa {MAX_REFERENCE_IMAGES})</Label>
              <input
                type="file"
                accept="image/*"
                multiple
                disabled={referenceImages.length >= MAX_REFERENCE_IMAGES}
                onChange={async (e) => {
                  const files = e.target.files;
                  if (!files || files.length === 0) return;
                  const room = MAX_REFERENCE_IMAGES - referenceImages.length;
                  const urls = await filesToDataUrls(files as unknown as FileList);
                  setReferenceImages((prev) => [...prev, ...urls.slice(0, room)]);
                  e.target.value = "";
                }}
                className="text-sm"
              />
              {referenceImages.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {referenceImages.map((src, i) => (
                    <div key={i} className="relative">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={src} alt="" className="h-16 w-16 object-cover rounded border border-border" />
                      <button
                        type="button"
                        onClick={() => setReferenceImages((prev) => prev.filter((_, j) => j !== i))}
                        className="absolute -top-1.5 -right-1.5 bg-destructive text-destructive-foreground rounded-full w-4 h-4 text-xs leading-none"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <Button type="submit" disabled={submitting || !prompt.trim()}>
              {submitting ? "Đang gửi..." : "Tạo ảnh / video"}
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Kết quả</CardTitle>
        </CardHeader>
        <CardContent>
          {!taskId && <p className="text-muted-foreground text-sm">Chưa có tác vụ nào.</p>}
          {taskId && (
            <div className="space-y-2 text-sm">
              <div>Mã tác vụ: <code>{taskId}</code></div>
              <div>Trạng thái: {event?.status ?? "đang gửi..."}</div>
              {event?.progress != null && <div>Tiến độ: {event.progress}%</div>}
              {event?.status === "failed" && <p className="text-destructive">{event.error}</p>}
              {event?.status === "completed" && (
                kind === "image" ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={resultUrl ?? ""} alt="" className="rounded border border-border max-w-full" />
                ) : (
                  <video src={resultUrl ?? ""} controls className="rounded border border-border max-w-full" />
                )
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
