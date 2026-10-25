"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError } from "@/lib/api";
import type { Account, Batch } from "@/lib/types";

const SIZES = ["1024x1024", "1280x720", "720x1280", "1080x1920"];

export default function BatchPage() {
  const [prompts, setPrompts] = useState<string[]>([]);
  const [kind, setKind] = useState<"image" | "video">("image");
  const [size, setSize] = useState("1280x720");
  const [duration, setDuration] = useState(10);
  const [concurrency, setConcurrency] = useState(1);
  const [accountId, setAccountId] = useState<string>("auto");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [importing, setImporting] = useState(false);
  const [creating, setCreating] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const loadBatches = useCallback(() => {
    api.get<Batch[]>("/admin/batches").then(setBatches).catch(() => {});
  }, []);

  useEffect(() => {
    api.get<{ accounts: Account[] }>("/admin/accounts").then((d) => setAccounts(d.accounts)).catch(() => {});
    loadBatches();
    const t = setInterval(loadBatches, 8000);
    return () => clearInterval(t);
  }, [loadBatches]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const body = await file.arrayBuffer();
      const res = await fetch(api.base + "/admin/batches/import", {
        method: "POST",
        credentials: "include",
        headers: { "X-Filename": file.name },
        body,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Import thất bại");
      }
      const data: { prompts: string[] } = await res.json();
      setPrompts(data.prompts);
      toast.success(`Đã đọc ${data.prompts.length} prompt`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Import thất bại");
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function onCreate() {
    if (prompts.length === 0) return;
    setCreating(true);
    try {
      await api.post("/admin/batches", {
        prompts,
        kind,
        size,
        duration,
        concurrency,
        account_id: accountId === "auto" ? null : accountId,
      });
      toast.success("Đã tạo lô");
      setPrompts([]);
      loadBatches();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Tạo lô thất bại");
    } finally {
      setCreating(false);
    }
  }

  async function control(bid: string, action: string) {
    try {
      await api.post(`/admin/batches/${bid}/${action}`);
      loadBatches();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Thao tác thất bại");
    }
  }

  function summarize(b: Batch) {
    const done = b.items.filter((i) => i.status === "completed").length;
    const failed = b.items.filter((i) => i.status === "failed").length;
    return `${done}/${b.items.length} xong${failed ? `, ${failed} lỗi` : ""}`;
  }

  return (
    <div className="space-y-6 max-w-4xl">
      <h1 className="text-xl font-semibold">Excel / TXT — Tạo hàng loạt</h1>

      <Card>
        <CardHeader><CardTitle className="text-base">Import prompt</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label>File .txt hoặc .xlsx (mỗi dòng/cột "prompt" một ảnh/video)</Label>
            <input ref={fileRef} type="file" accept=".txt,.xlsx" onChange={onFile} disabled={importing}
              className="text-sm" />
          </div>
          {prompts.length > 0 && (
            <>
              <p className="text-sm text-muted-foreground">Đã đọc {prompts.length} prompt.</p>
              <div className="flex gap-3 flex-wrap">
                <div className="space-y-2">
                  <Label>Loại</Label>
                  <Select value={kind} onValueChange={(v) => v && setKind(v as "image" | "video")}>
                    <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="image">Ảnh</SelectItem>
                      <SelectItem value="video">Video</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Kích thước</Label>
                  <Select value={size} onValueChange={(v) => v && setSize(v)}>
                    <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {SIZES.map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                {kind === "video" && (
                  <div className="space-y-2">
                    <Label>Giây</Label>
                    <Select value={String(duration)} onValueChange={(v) => v && setDuration(Number(v))}>
                      <SelectTrigger className="w-24"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {[5, 10].map((d) => <SelectItem key={d} value={String(d)}>{d}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                )}
                <div className="space-y-2">
                  <Label>Song song</Label>
                  <Select value={String(concurrency)} onValueChange={(v) => v && setConcurrency(Number(v))}>
                    <SelectTrigger className="w-24"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="1">1</SelectItem>
                      <SelectItem value="2">2</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Tài khoản</Label>
                  <Select value={accountId} onValueChange={(v) => v && setAccountId(v)}>
                    <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="auto">Tự động chọn</SelectItem>
                      {accounts.filter((a) => a.enabled).map((a) => (
                        <SelectItem key={a.id} value={a.id}>{a.label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <Button onClick={onCreate} disabled={creating}>
                {creating ? "Đang tạo..." : `Tạo lô ${prompts.length} prompt`}
              </Button>
            </>
          )}
        </CardContent>
      </Card>

      <div className="space-y-2">
        <h2 className="font-medium">Các lô đã tạo</h2>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mã lô</TableHead>
              <TableHead>Loại</TableHead>
              <TableHead>Tài khoản</TableHead>
              <TableHead>Tiến độ</TableHead>
              <TableHead>Trạng thái</TableHead>
              <TableHead className="text-right">Thao tác</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {batches.length === 0 ? (
              <TableRow><TableCell colSpan={6} className="text-center text-muted-foreground">Chưa có lô nào.</TableCell></TableRow>
            ) : (
              batches.map((b) => (
                <TableRow key={b.id}>
                  <TableCell className="font-mono text-xs">{b.id}</TableCell>
                  <TableCell><Badge variant="outline">{b.kind}</Badge></TableCell>
                  <TableCell className="text-sm">{b.account_label}</TableCell>
                  <TableCell className="text-sm">{summarize(b)}</TableCell>
                  <TableCell className="text-sm">{b.paused ? `Tạm dừng — ${b.pause_reason}` : "Đang chạy"}</TableCell>
                  <TableCell className="text-right space-x-1">
                    {b.paused ? (
                      <Button size="sm" variant="outline" onClick={() => control(b.id, "resume")}>Tiếp tục</Button>
                    ) : (
                      <Button size="sm" variant="outline" onClick={() => control(b.id, "pause")}>Tạm dừng</Button>
                    )}
                    <Button size="sm" variant="outline" onClick={() => control(b.id, "retry-failed")}>Tạo lại lỗi</Button>
                    <Button size="sm" variant="destructive" onClick={() => control(b.id, "stop")}>Dừng</Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
