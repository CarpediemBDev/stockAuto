"use client";

import React, { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useAuthStore } from "@/store/authStore";
import { Dashboard } from "@/components/Dashboard";
import MarketHeader from "@/components/MarketHeader";

export default function Home() {
  const router = useRouter();
  const { isAuthenticated, isInitialized } = useAuthStore();
  const t = useTranslations("dashboard");

  useEffect(() => {
    if (isInitialized && !isAuthenticated) {
      router.push("/login");
    }
  }, [isInitialized, isAuthenticated, router]);

  if (!isInitialized || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-black flex items-center justify-center text-zinc-400 text-sm">
        {t("auth_checking")}
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
