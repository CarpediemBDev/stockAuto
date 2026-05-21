"use client";

import React, { useEffect, useState, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { botAPI } from "@/lib/api";
import { toast } from "sonner";

const navItems = [
  { href: "/", label: "📈 Auto Trading" },
  { href: "/scanner", label: "🔭 Market Scanner" },
  { href: "/admin/settings", label: "⚙️ System Admin" },
];

export function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [tradeMode, setTradeMode] = useState("VIRTUAL");
  const [isRealEnabled, setIsRealEnabled] = useState(false);
  const [username, setUsername] = useState<string | null>(null);

  // 현재 사용자명 읽기
  useEffect(() => {
    if (typeof window !== "undefined") {
      setUsername(localStorage.getItem("stockauto_username"));
    }
  }, [pathname]); // 경로 이동 시 갱신

  const fetchStatus = useCallback(async () => {
    // 토큰이 있을 때만 API 호출 (무한 401 및 리다이렉트 방지)
    if (!localStorage.getItem("stockauto_token")) {
      return;
    }
    try {
      const res = await botAPI.getStatus();
      setTradeMode(res.data.trade_mode);
      setIsRealEnabled(res.data.is_real_enabled);
    } catch (error) {
      // Silently fail in navbar background fetches
    }
  }, []);

  useEffect(() => {
    const initFetch = async () => {
      await fetchStatus();
    };
    initFetch();
    
    const interval = setInterval(fetchStatus, 8000); // 8초 주기로 전역 상태 동기화
    return () => clearInterval(interval);
  }, [fetchStatus]);

  const handleLogout = () => {
    localStorage.removeItem("stockauto_token");
    localStorage.removeItem("stockauto_username");
    setUsername(null);
    toast.success("성공적으로 로그아웃되었습니다.");
    router.push("/login");
  };

  // 로그인 및 회원가입 페이지에서는 상단 바를 최소화하여 렌더링
  const isAuthPage = pathname.startsWith("/login") || pathname.startsWith("/signup");

  return (
    <nav className="sticky top-0 z-50 w-full backdrop-blur-md bg-black/50 border-b border-zinc-800">
      <div className="max-w-[1600px] mx-auto px-6">
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
            {!isAuthPage && username && (
              <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider transition-colors duration-500 select-none ${
                tradeMode === 'REAL' 
                  ? (isRealEnabled ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-red-900/40 text-red-300 border border-red-700/50') 
                  : tradeMode === 'MOCK'
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              }`}>
                {tradeMode === 'REAL' 
                  ? (isRealEnabled ? '🔥 PREMIUM / LIVE' : '🔒 PREMIUM / REAL (LOCKED)') 
                  : tradeMode === 'MOCK'
                  ? '⚡ PRO / MOCK'
                  : '📝 FREE / SIMULATED'}
              </span>
            )}
          </Link>

          {/* 메뉴 및 사용자 계정 영역 */}
          {!isAuthPage && (
            <div className="flex items-center space-x-6">
              {/* 메인 메뉴 링크 */}
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

              {/* 사용자 계정 & 로그아웃 버튼 */}
              {username && (
                <div className="flex items-center space-x-4 border-l border-zinc-800 pl-6">
                  <div className="flex flex-col text-right">
                    <span className="text-xs text-zinc-400">Welcome</span>
                    <span className="text-sm font-semibold text-white">{username}님</span>
                  </div>
                  <button
                    onClick={handleLogout}
                    className="px-3.5 py-1.5 rounded-lg border border-zinc-800 hover:border-red-500/30 hover:bg-red-500/10 text-zinc-400 hover:text-red-400 text-xs font-semibold active:scale-[0.98] transition-all duration-200"
                  >
                    로그아웃
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
