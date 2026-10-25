"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ApiError } from "@/lib/api";

interface AddResult {
  added: { id: string; label: string; cookie_count: number }[];
  essential_missing: string[];
  warning: string;
}

export default function AddAccountPage() {
  const [label, setLabel] = useState("");
  const [cookieText, setCookieText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AddResult | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!cookieText.trim()) return;
    setLoading(true);
    setResult(null);
    try {
      const batch = label.trim() && !cookieText.includes("|")
        ? `${label.trim()} | ${cookieText.trim()}`
        : cookieText.trim();
      const data = await api.post<AddResult>("/admin/accounts", { batch });
      setResult(data);
      if (data.warning) toast.warning(data.warning);
      else toast.success(`Đã thêm ${data.added.length} tài khoản`);
      setCookieText("");
      setLabel("");
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Không thêm được tài khoản");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4 max-w-2xl">
      <h1 className="text-xl font-semibold">Thêm tài khoản</h1>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dán Cookie đăng nhập muse.ai</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="label">Tên gợi nhớ (không bắt buộc)</Label>
              <Input id="label" value={label} onChange={(e) => setLabel(e.target.value)}
                placeholder="Ví dụ: tài khoản chính" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cookie">Cookie đăng nhập</Label>
              <Textarea id="cookie" rows={6} value={cookieText}
                onChange={(e) => setCookieText(e.target.value)}
                placeholder={"Dán Cookie vào đây.\nNhiều tài khoản: mỗi dòng một tài khoản, dạng tên | Cookie"} />
            </div>
            <Button type="submit" disabled={loading || !cookieText.trim()}>
              {loading ? "Đang thêm..." : "Nhập Cookie"}
            </Button>
          </form>
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Kết quả</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {result.added.map((a) => (
              <div key={a.id}>✓ {a.label} — {a.cookie_count} cookie</div>
            ))}
            {result.warning && <p className="text-amber-500">{result.warning}</p>}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
