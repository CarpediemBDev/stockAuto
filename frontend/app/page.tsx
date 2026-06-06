"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { Dashboard } from "@/components/Dashboard";
import MarketHeader from "@/components/MarketHeader";

export default function Home() {
  const router = useRouter();
  const { isAuthenticated, isInitialized } = useAuthStore();

  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.push("/login");
    }
  }, [isInitialized, isAuthenticated, router]);

  if (!isInitialized || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-black flex items-center justify-center text-zinc-400 text-sm">
        인증 정보 확인 중...
      </div>
    );
  }

  return (
    <main className="min-h-screen bg-[#020617] text-slate-200">
      <MarketHeader />
      <Dashboard />
    </main>
  );
}
