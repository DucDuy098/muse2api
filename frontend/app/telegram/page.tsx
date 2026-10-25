"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, ApiError } from "@/lib/api";

interface TelegramStatus {
  enabled: boolean;
  user_ids: number[];
  send_original: boolean;
  token_set: boolean;
  running: boolean;
  connected: boolean;
  username: string;
  error: string;
}

export default function TelegramPage() {
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [token, setToken] = useState("");
  const [userIds, setUserIds] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [sendOriginal, setSendOriginal] = useState(true);
  const [saving, setSaving] = useState(false);

  function load() {
    api.get<TelegramStatus>("/admin/telegram/settings").then((d) => {
      setStatus(d);
      setUserIds(d.user_ids.join(", "));
      setEnabled(d.enabled);
      setSendOriginal(d.send_original);
    }).catch((err) => toast.error(err instanceof ApiError ? err.message : "Không tải được cấu hình"));
  }

  useEffect(load, []);

  async function save() {
    setSaving(true);
    try {
      const body: Record<string, unknown> = { enabled, send_original: sendOriginal, user_ids: userIds };
      if (token.trim()) body.token = token.trim();
      await api.post("/admin/telegram/settings", body);
      setToken("");
      toast.success("Đã lưu cấu hình Telegram");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Lưu thất bại");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4 max-w-xl">
      <h1 className="text-xl font-semibold">Telegram Bot</h1>
      <Card>
        <CardHeader><CardTitle className="text-base">Cấu hình</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <input type="checkbox" id="enabled" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
            <Label htmlFor="enabled">Bật bot</Label>
          </div>
          <div className="space-y-2">
            <Label htmlFor="token">
              Bot token {status?.token_set && <span className="text-muted-foreground">(đã có, để trống nếu giữ nguyên)</span>}
            </Label>
            <Input id="token" type="password" value={token} onChange={(e) => setToken(e.target.value)}
              placeholder={status?.token_set ? "••••••••" : "123456:ABC-DEF..."} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ids">Telegram User ID được phép (cách nhau dấu phẩy)</Label>
            <Input id="ids" value={userIds} onChange={(e) => setUserIds(e.target.value)} placeholder="123456789, 987654321" />
          </div>
          <div className="flex items-center gap-2">
            <input type="checkbox" id="orig" checked={sendOriginal} onChange={(e) => setSendOriginal(e.target.checked)} />
            <Label htmlFor="orig">Giữ ảnh gốc (gửi dạng file thay vì nén)</Label>
          </div>
          <Button onClick={save} disabled={saving}>{saving ? "Đang lưu..." : "Lưu"}</Button>
        </CardContent>
      </Card>

      {status && (
        <Card>
          <CardHeader><CardTitle className="text-base">Trạng thái</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex gap-2 items-center">
              <Badge variant={status.running ? "default" : "secondary"}>{status.running ? "Đang chạy" : "Đã dừng"}</Badge>
              <Badge variant={status.connected ? "default" : "outline"}>{status.connected ? "Đã kết nối" : "Chưa kết nối"}</Badge>
            </div>
            {status.username && <div>Bot: @{status.username}</div>}
            {status.error && <p className="text-destructive">{status.error}</p>}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
