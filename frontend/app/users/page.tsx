"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, ApiError, hasRole, type Role } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { fmtTime } from "@/lib/types";

interface User {
  id: number;
  username: string;
  role: Role;
  enabled: boolean;
  created_at: string;
  last_login_at: string | null;
}

const ROLES: Role[] = ["viewer", "member", "admin", "owner"];

export default function UsersPage() {
  const { me } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    api.get<{ items: User[] }>("/admin/users")
      .then((d) => setUsers(d.items))
      .catch((err) => toast.error(err instanceof ApiError ? err.message : "Không tải được danh sách"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const canManage = hasRole(me, "owner");

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    setCreating(true);
    try {
      await api.post("/admin/users", { username, password, role });
      toast.success("Đã tạo user " + username);
      setUsername("");
      setPassword("");
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Tạo user thất bại");
    } finally {
      setCreating(false);
    }
  }

  async function changeRole(u: User, newRole: Role) {
    try {
      await api.patch(`/admin/users/${u.id}`, { role: newRole });
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Đổi role thất bại");
    }
  }

  async function toggleEnabled(u: User) {
    try {
      await api.patch(`/admin/users/${u.id}`, { enabled: !u.enabled });
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Thao tác thất bại");
    }
  }

  async function remove(u: User) {
    if (!confirm(`Xoá user "${u.username}"?`)) return;
    try {
      await api.delete(`/admin/users/${u.id}`);
      load();
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Xoá thất bại");
    }
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Người dùng</h1>

      {canManage && (
        <Card className="max-w-3xl">
          <CardHeader><CardTitle className="text-base">Thêm user</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={onCreate} className="flex gap-3 items-end flex-wrap">
              <div className="space-y-2">
                <Label>Tên đăng nhập</Label>
                <Input value={username} onChange={(e) => setUsername(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>Mật khẩu</Label>
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
              </div>
              <div className="space-y-2">
                <Label>Role</Label>
                <Select value={role} onValueChange={(v) => v && setRole(v as Role)}>
                  <SelectTrigger className="w-32"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <Button type="submit" disabled={creating}>{creating ? "Đang tạo..." : "Tạo"}</Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Tên đăng nhập</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Trạng thái</TableHead>
            <TableHead>Đăng nhập gần nhất</TableHead>
            {canManage && <TableHead className="text-right">Thao tác</TableHead>}
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow><TableCell colSpan={5} className="text-center text-muted-foreground">Đang tải...</TableCell></TableRow>
          ) : (
            users.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">{u.username}</TableCell>
                <TableCell>
                  {canManage ? (
                    <Select value={u.role} onValueChange={(v) => v && changeRole(u, v as Role)}>
                      <SelectTrigger className="w-28"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {ROLES.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  ) : (
                    <Badge variant="outline">{u.role}</Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={u.enabled ? "default" : "secondary"}>{u.enabled ? "Hoạt động" : "Đã tắt"}</Badge>
                </TableCell>
                <TableCell className="text-sm">{u.last_login_at ? fmtTime(Math.floor(new Date(u.last_login_at).getTime() / 1000)) : "—"}</TableCell>
                {canManage && (
                  <TableCell className="text-right space-x-1">
                    <Button size="sm" variant="outline" onClick={() => toggleEnabled(u)}>
                      {u.enabled ? "Tắt" : "Bật"}
                    </Button>
                    <Button size="sm" variant="destructive" onClick={() => remove(u)}>Xoá</Button>
                  </TableCell>
                )}
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  );
}
