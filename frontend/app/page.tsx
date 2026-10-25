"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export default function Home() {
  const router = useRouter();
  const { me, loading } = useAuth();

  useEffect(() => {
    if (!loading && me) router.replace("/tasks");
  }, [loading, me, router]);

  return null;
}
