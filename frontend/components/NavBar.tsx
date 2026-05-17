"use client";

import React, { useEffect, useState, useCallback } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { botAPI } from "@/lib/api";

const navItems = [
  { href: "/", label: "📈 Auto Trading" },
  { href: "/scanner", label: "🔭 Market Scanner" },
  { href: "/admin", label: "⚙️ System Admin" },
];

export function NavBar() {
  const pathname = usePathname();
  const [tradeMode, setTradeMode] = useState("VIRTUAL");
  const [isRealEnabled, setIsRealEnabled] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await botAPI.getStatus();
      setTradeMode(res.data.trade_mode);
      setIsRealEnabled(res.data.is_real_enabled);
    } catch (error) {
      // Silently fail or keep virtual during background fetches in navbar
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 8000); // 8초 주기로 전역 상태 동기화
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-black/50 border-b border-zinc-800">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* 로고 영역 */}
          <Link href="/" className="flex-shrink-0 flex items-center gap-3 group">
            <div className="w-8 h-8 rounded bg-gradient-to-br from-blue-500 to-emerald-500 flex items-center justify-center font-bold text-white group-hover:scale-110 transition-transform">
              SA
            </div>
            <div className="flex flex-col">
              <span className="font-bold text-base tracking-tight leading-none">StockAuto</span>
              <span className="text-[9px] text-zinc-500 mt-1 leading-none">QUANT PLATFORM</span>
            </div>
            <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider transition-colors duration-500 select-none ${
              tradeMode === 'REAL' 
                ? (isRealEnabled ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30') 
                : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
            }`}>
              {tradeMode === 'REAL' 
                ? (isRealEnabled ? 'PRO / LIVE' : 'PRO / REAL') 
                : 'FREE / VIRTUAL'}
            </span>
          </Link>

          {/* 메뉴 영역 */}
          <div className="flex space-x-2">
            {navItems.map((item) => {
              const isActive =
                item.href === "/"
                  ? pathname === "/"
                  : pathname.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200",
                    isActive
                      ? "bg-zinc-800 text-white shadow-inner"
                      : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </div>
        </div>
      </div>
    </nav>
  );
}
