"use client";

import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import { fmtTime, type Task } from "@/lib/types";

const STATUS_LABEL: Record<string, string> = {
  queued: "Đang chờ",
  processing: "Đang tạo",
  completed: "Hoàn thành",
  failed: "Lỗi",
};

export default function TasksPage() {
  const { me } = useAuth();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.get<{ tasks: Task[] }>("/admin/tasks");
      setTasks(data.tasks);
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : "Không tải được danh sách tác vụ");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const interval = setInterval(load, 10000);
    return () => clearInterval(interval);
  }, [load]);

  const canDelete = hasRole(me, "member");

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Tác vụ</h1>
        <Button variant="outline" onClick={() => load()}>Làm mới</Button>
      </div>
      <div className="rounded border border-border overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Mã</TableHead>
              <TableHead>Loại</TableHead>
              <TableHead>Mô tả</TableHead>
              <TableHead>Trạng thái</TableHead>
              <TableHead>Tài khoản</TableHead>
              <TableHead>Tạo lúc</TableHead>
              <TableHead className="text-right">Thao tác</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">Đang tải...</TableCell></TableRow>
            ) : tasks.length === 0 ? (
              <TableRow><TableCell colSpan={7} className="text-center text-muted-foreground">Chưa có tác vụ nào.</TableCell></TableRow>
            ) : (
              tasks.map((t) => (
                <TableRow key={t.id}>
                  <TableCell className="font-mono text-xs">{t.id}</TableCell>
                  <TableCell><Badge variant="outline">{t.kind}</Badge></TableCell>
                  <TableCell className="max-w-80 truncate text-sm" title={t.prompt}>{t.prompt}</TableCell>
                  <TableCell>
                    <Badge variant={t.status === "failed" ? "destructive" : t.status === "completed" ? "default" : "secondary"}>
                      {STATUS_LABEL[t.status] ?? t.status}
                      {t.status === "processing" && t.progress != null ? ` ${t.progress}%` : ""}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm">{t.account_label ?? t.account ?? "—"}</TableCell>
                  <TableCell className="text-sm">{fmtTime(t.created_at)}</TableCell>
                  <TableCell className="text-right space-x-1">
                    <Dialog>
                      <DialogTrigger render={<Button size="sm" variant="outline" />}>
                        Chi tiết
                      </DialogTrigger>
                      <DialogContent className="sm:max-w-lg">
                        <DialogHeader>
                          <DialogTitle className="font-mono text-sm">{t.id}</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-3 text-sm">
                          <div className="flex items-center gap-2">
                            <Badge variant="outline">{t.kind}</Badge>
                            <Badge variant={t.status === "failed" ? "destructive" : t.status === "completed" ? "default" : "secondary"}>
                              {STATUS_LABEL[t.status] ?? t.status}
                            </Badge>
                          </div>
                          {t.status === "processing" && t.progress != null && (
                            <div className="space-y-1">
                              <div className="flex justify-between text-xs text-muted-foreground">
                                <span>Tiến độ</span>
                                <span>{t.progress}%</span>
                              </div>
                              <Progress value={t.progress} />
                            </div>
                          )}
                          <div>
                            <div className="text-xs text-muted-foreground mb-1">Mô tả</div>
                            <p className="whitespace-pre-wrap">{t.prompt}</p>
                          </div>
                          <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
                            <div>Tài khoản: {t.account_label ?? t.account ?? "—"}</div>
                            <div>Tạo lúc: {fmtTime(t.created_at)}</div>
                          </div>
                          {t.status === "failed" && t.error && (
                            <div>
                              <div className="text-xs text-muted-foreground mb-1">Lỗi</div>
                              <p className="text-destructive whitespace-pre-wrap">{t.error}</p>
                            </div>
                          )}
                          {t.status === "completed" && (() => {
                            const mediaUrl = t.url ?? t.result?.url;
                            if (!mediaUrl) return null;
                            return t.kind === "video" ? (
                              <video src={api.base + mediaUrl} controls className="rounded border border-border max-w-full" />
                            ) : (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={api.base + mediaUrl} alt="" className="rounded border border-border max-w-full" />
                            );
                          })()}
                        </div>
                      </DialogContent>
                    </Dialog>
                    {canDelete && (
                      <Button size="sm" variant="outline"
                        onClick={async () => {
                          try {
                            await api.delete(`/admin/tasks/${t.id}`);
                            load();
                          } catch (err) {
                            toast.error(err instanceof ApiError ? err.message : "Xoá thất bại");
                          }
                        }}>
                        Xoá
                      </Button>
                    )}
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
