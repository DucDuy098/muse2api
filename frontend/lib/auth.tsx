"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useRouter, usePathname } from "next/navigation";
import { api, ApiError, type Me } from "./api";

interface AuthState {
  me: Me | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();
  const pathname = usePathname();

  async function refresh() {
    try {
      const data = await api.get<Me>("/auth/me");
      setMe(data);
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }

  async function logout() {
    try {
      await api.post("/auth/logout");
    } finally {
      setMe(null);
      router.push("/login");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!loading && !me && pathname !== "/login") {
      router.replace("/login");
    }
  }, [loading, me, pathname, router]);

  return (
    <AuthContext.Provider value={{ me, loading, refresh, logout }}>{children}</AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export { ApiError };
