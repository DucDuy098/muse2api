"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useAuth } from "@/lib/auth";
import { hasRole, type Role } from "@/lib/api";
import { Button } from "@/components/ui/button";

interface NavItem {
  href: string;
  label: string;
  minRole: Role;
}

const NAV: NavItem[] = [
  { href: "/chat", label: "Chat Muse", minRole: "viewer" },
  { href: "/playground", label: "Tạo ảnh / video", minRole: "viewer" },
  { href: "/tasks", label: "Tác vụ", minRole: "viewer" },
  { href: "/library", label: "Thư viện", minRole: "viewer" },
  { href: "/batch", label: "Excel / TXT", minRole: "member" },
  { href: "/accounts", label: "Tài khoản", minRole: "viewer" },
  { href: "/accounts/add", label: "Thêm tài khoản", minRole: "member" },
  { href: "/telegram", label: "Telegram", minRole: "admin" },
  { href: "/docs", label: "Hướng dẫn API", minRole: "viewer" },
  { href: "/users", label: "Người dùng", minRole: "admin" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { me, loading, logout } = useAuth();

  if (pathname === "/login") {
    return <main className="flex-1 flex items-center justify-center">{children}</main>;
  }

  if (loading) {
    return <main className="flex-1 flex items-center justify-center text-muted-foreground">Đang tải...</main>;
  }

  if (!me) {
    // AuthProvider is already redirecting to /login; render nothing meanwhile.
    return null;
  }

  return (
    <div className="flex flex-1 min-h-0">
      <aside className="w-56 shrink-0 border-r border-border flex flex-col">
        <div className="px-4 py-4 font-semibold">Muse2API Studio</div>
        <nav className="flex-1 overflow-y-auto px-2 space-y-1">
          {NAV.filter((item) => hasRole(me, item.minRole)).map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded px-3 py-2 text-sm hover:bg-accent ${
                pathname === item.href ? "bg-accent font-medium" : "text-muted-foreground"
              }`}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="border-t border-border px-4 py-3 text-sm">
          <div className="font-medium">{me.username}</div>
          <div className="text-muted-foreground mb-2">{me.role}</div>
          <Button variant="outline" size="sm" className="w-full" onClick={() => logout()}>
            Đăng xuất
          </Button>
        </div>
      </aside>
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
