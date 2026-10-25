"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { api, ApiError, hasRole } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime, type Account, type AccountStats } from "@/lib/types";

export default function AccountsPage() {
  const { me } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [stats, setStats] = useState<AccountStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ accounts: Account[]; stats: AccountStats }>("/admin/accounts");
      setAccounts(data.accounts);
      setStats(data.stats);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Không tải được danh sách tài khoản");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function run(aid: string, action: () => Promise<unknown>, label: string) {
    setBusy(aid);
    try {
      await action();
      toast.success(label + " thành công");
      await load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : label + " thất bại");
    } finally {
      setBusy(null);
    }
  }

  const canWrite = hasRole(me, "member");
  const canDelete = hasRole(me, "admin");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tài khoản</h1>
        <Button variant="outline" onClick={() => load()}>Làm mới</Button>
      </div>

      {stats && (
        <div className="grid grid-cols-2 sm:grid-cols-6 gap-3">
          {[
            ["Tổng", stats.total],
            ["Bật", stats.enabled],
            ["Tắt", stats.disabled],
            ["Sống", stats.healthy],
            ["Lỗi", stats.error],
            ["Sắp hết hạn", stats.expiring],
          ].map(([label, value]) => (
            <div key={label as string} className="rounded border border-border p-3">
              <div className="text-2xl font-semibold">{value}</div>
              <div className="text-xs text-muted-foreground">{label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="rounded border border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tên</TableHead>
              <TableHead>Trạng thái</TableHead>
              <TableHead>Hết hạn</TableHead>
              <TableHead>Cookie</TableHead>
              <TableHead>Dùng gần nhất</TableHead>
              <TableHead>Ghi chú</TableHead>
              {canWrite && <TableHead className="text-right">Thao tác</TableHead>}
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">Đang tải...</TableCell></TableRow>
            ) : accounts.length === 0 ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">Chưa có tài khoản nào.</TableCell></TableRow>
            ) : (
              accounts.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="font-medium">{a.label}</TableCell>
                  <TableCell className="space-x-1">
                    <Badge variant={a.ok === false ? "destructive" : a.ok ? "default" : "secondary"}>
                      {a.ok === false ? "Gặp lỗi" : a.ok ? "Sẵn sàng" : "Chưa kiểm tra"}
                    </Badge>
                    {!a.essential_ok && <Badge variant="outline">Thiếu Cookie</Badge>}
                    {!a.enabled && <Badge variant="outline">Đã tắt</Badge>}
                  </TableCell>
                  <TableCell className="text-sm">{fmtTime(a.expires_at)}</TableCell>
                  <TableCell className="text-sm">{a.cookie_count}</TableCell>
                  <TableCell className="text-sm">{fmtTime(a.last_used)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground max-w-50 truncate" title={a.note}>{a.note || "—"}</TableCell>
                  {canWrite && (
                    <TableCell className="text-right space-x-1 whitespace-nowrap">
                      <Button size="sm" variant="outline" disabled={busy === a.id}
                        onClick={() => run(a.id, () => api.post(`/admin/accounts/${a.id}/test`), "Kiểm tra")}>
                        Kiểm tra
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy === a.id}
                        onClick={() => run(a.id, () => api.post(`/admin/accounts/${a.id}/relogin`), "Làm mới")}>
                        Làm mới
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy === a.id}
                        onClick={() => run(a.id, () => api.patch(`/admin/accounts/${a.id}`, { enabled: !a.enabled }), a.enabled ? "Tắt" : "Bật")}>
                        {a.enabled ? "Tắt" : "Bật"}
                      </Button>
                      {canDelete && (
                        <Button size="sm" variant="destructive" disabled={busy === a.id}
                          onClick={() => {
                            if (confirm(`Xoá tài khoản "${a.label}"?`)) run(a.id, () => api.delete(`/admin/accounts/${a.id}`), "Xoá");
                          }}>
                          Xoá
                        </Button>
                      )}
                    </TableCell>
                  )}
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
