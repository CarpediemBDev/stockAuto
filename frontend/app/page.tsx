"use client";

import React, { useEffect, useState, startTransition } from "react";
import { useRouter } from "next/navigation";
import { Dashboard } from "@/components/Dashboard";
import MarketHeader from "@/components/MarketHeader";

export default function Home() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("stockauto_token");
    if (!token) {
      router.push("/login");
    } else {
      startTransition(() => {
        setIsAuthenticated(true);
      });
    }
  }, [router]);


  if (!isAuthenticated) {
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
