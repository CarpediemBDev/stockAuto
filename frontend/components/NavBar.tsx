"use client";

import React, { useState, useRef, useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import Link from "next/link";

import useSWR from "swr";
import { cn } from "@/lib/utils";
import { authAPI, botAPI, fetcher } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { useTimezone } from "@/store/timezoneStore";
import { toast } from "sonner";
import { Globe, Activity } from "lucide-react";

// 모바일(<md)에서는 아이콘만 노출해 가로 오버플로를 막는다
const navItems = [
  { href: "/", icon: "📈", text: "자동 매매" },
  { href: "/scanner", icon: "🔭", text: "마켓 스캐너" },
  { href: "/report", icon: "📊", text: "매매 보고서" },
];

export function NavBar() {
  const pathname = usePathname();
  const router = useRouter();
  const [isTogglingBot, setIsTogglingBot] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const [isTimezoneMenuOpen, setIsTimezoneMenuOpen] = useState(false);
  const { accessToken, username, role, clearAuth } = useAuthStore();
  const { selectedTimezone, timezoneOptions, setTimezone } = useTimezone();

  const userMenuRef = useRef<HTMLDivElement>(null);
  const timezoneMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (isUserMenuOpen && userMenuRef.current && !userMenuRef.current.contains(event.target as Node)) {
        setIsUserMenuOpen(false);
      }
      if (isTimezoneMenuOpen && timezoneMenuRef.current && !timezoneMenuRef.current.contains(event.target as Node)) {
        setIsTimezoneMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [isUserMenuOpen, isTimezoneMenuOpen]);

  const { data: statusData, mutate } = useSWR(
    accessToken ? '/bot/status' : null,
    fetcher,
    { refreshInterval: 15000 }
  );

  const tradeMode = statusData?.trade_mode || "VIRTUAL";
  const isBotRunning = statusData?.is_running || false;

  const handleToggleBot = async () => {
    setIsTogglingBot(true);
    try {
      if (isBotRunning) {
        await botAPI.stop();
        toast.success("자율 트레이딩 자동매매 루프를 정지했습니다.");
      } else {
        await botAPI.start();
        toast.success("자율 트레이딩 자동매매 루프를 가동했습니다.");
      }
      mutate();
    } catch (error: unknown) {
      const errMsg = error instanceof Error ? error.message : "봇 제어에 실패했습니다.";
      toast.error(errMsg);
    } finally {
      setIsTogglingBot(false);
    }

  };

  const handleLogout = async () => {
    try {
      await authAPI.logout();
    } catch {
      // 무시
    }
    clearAuth();
    toast.success("성공적으로 로그아웃되었습니다.");
    router.push("/login");
  };

  // 로그인 및 회원가입 페이지에서는 상단 바를 최소화하여 렌더링
  const isAuthPage = pathname.startsWith("/login") || pathname.startsWith("/signup");

  return (
    <nav className="sticky top-0 z-[100] w-full backdrop-blur-md bg-black/50 border-b border-zinc-800">
      <div className="max-w-[1600px] mx-auto px-3 md:px-6">
        <div className="flex items-center justify-between h-16">
          {/* 로고 영역 */}
          <Link href="/" className="flex-shrink-0 flex items-center gap-3 group">
            <div className="w-8 h-8 rounded bg-gradient-to-br from-blue-500 to-emerald-500 flex items-center justify-center font-bold text-white group-hover:scale-110 transition-transform">
              SA
            </div>
            <div className="hidden sm:flex flex-col">
              <span className="font-bold text-base tracking-tight leading-none">StockAuto</span>
              <span className="text-[11px] text-zinc-500 mt-1 leading-none">QUANT PLATFORM</span>
            </div>
            {!isAuthPage && username && (
              <span className={`hidden md:inline-block px-2 py-0.5 rounded text-[11px] font-black uppercase tracking-wider transition-colors duration-500 select-none whitespace-nowrap ${
                tradeMode === 'REAL'
                  ? (isBotRunning ? 'bg-red-500/20 text-red-400 border border-red-500/30' : 'bg-red-900/40 text-red-300 border border-red-700/50')
                  : tradeMode === 'MOCK'
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
              }`}>
                {tradeMode === 'REAL'
                  ? (isBotRunning ? '🔥 PREMIUM / LIVE' : '🔒 PREMIUM / REAL (STOPPED)')
                  : tradeMode === 'MOCK'
                  ? '⚡ PRO / MOCK'
                  : '📝 FREE / SIMULATED'}
              </span>
            )}
          </Link>

          {/* 메뉴 및 사용자 계정 영역 */}
          {!isAuthPage && (
            <div className="flex items-center space-x-2 md:space-x-6">
              {/* 메인 메뉴 링크 */}
              <div className="flex space-x-1 md:space-x-2">
                {navItems.map((item) => {
                  const isActive =
                    item.href === "/"
                      ? pathname === "/"
                      : pathname.startsWith(item.href);

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      title={item.text}
                      className={cn(
                        "px-3 md:px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 whitespace-nowrap",
                        isActive
                          ? "bg-zinc-800 text-white shadow-inner"
                          : "text-zinc-400 hover:text-white hover:bg-zinc-800/50"
                      )}
                    >
                      {item.icon} <span className="hidden md:inline">{item.text}</span>
                    </Link>
                  );
                })}
              </div>

              {/* 사용자 계정 프로필 및 타임존 드롭다운 */}
              {username && (
                <div className="flex items-center space-x-2 md:space-x-4 border-l border-zinc-800 pl-2 md:pl-6">
                  {/* 타임존 스위처 */}
                  <div ref={timezoneMenuRef} className="relative flex items-center">
                    <button
                      onClick={() => {
                        setIsTimezoneMenuOpen(!isTimezoneMenuOpen);
                        setIsUserMenuOpen(false);
                      }}
                      className="flex items-center justify-center w-8 h-8 rounded-full hover:bg-zinc-800/50 text-zinc-400 hover:text-white transition-colors duration-200"
                      title="타임존 변경"
                    >
                      <Globe size={18} />
                    </button>
                    
                    {isTimezoneMenuOpen && (
                      <>
                        <div className="absolute right-0 top-10 mt-2 w-48 rounded-2xl bg-zinc-900/95 backdrop-blur-xl border border-zinc-800 shadow-2xl py-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                          <div className="px-3 pb-2 border-b border-zinc-800/60 mb-1">
                            <p className="text-[11px] text-zinc-500 font-bold uppercase tracking-wider">Timezone</p>
                          </div>
                          <div className="px-1.5 space-y-0.5">
                            {timezoneOptions.map((tz) => (
                              <button
                                key={tz.id}
                                onClick={() => {
                                  setTimezone(tz.id);
                                  setIsTimezoneMenuOpen(false);
                                  toast.success(`타임존이 ${tz.abbr} 기준으로 변경되었습니다.`);
                                }}
                                className={cn(
                                  "w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-semibold transition-all duration-200",
                                  selectedTimezone.id === tz.id 
                                    ? "bg-indigo-500/20 text-indigo-400" 
                                    : "text-zinc-400 hover:bg-zinc-800 hover:text-white"
                                )}
                              >
                                <span>{tz.label}</span>
                                {selectedTimezone.id === tz.id && (
                                  <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 shadow-[0_0_8px_rgba(99,102,241,0.8)]"></span>
                                )}
                              </button>
                            ))}
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  <div ref={userMenuRef} className="relative flex items-center">
                    <button
                      onClick={() => {
                        setIsUserMenuOpen(!isUserMenuOpen);
                        setIsTimezoneMenuOpen(false);
                      }}
                      className="flex items-center space-x-2.5 px-3.5 py-1.5 rounded-xl border border-zinc-800 hover:border-zinc-700 bg-zinc-950/40 hover:bg-zinc-900/50 text-white font-semibold text-xs tracking-tight transition-all duration-200 active:scale-[0.98] cursor-pointer"
                    >
                    <span className={cn("w-1.5 h-1.5 rounded-full animate-pulse", isBotRunning ? "bg-emerald-500" : "bg-zinc-500")}></span>
                    <span>{username}님</span>
                    <svg
                      className={cn("w-3.5 h-3.5 text-zinc-400 transition-transform duration-200", isUserMenuOpen && "rotate-180")}
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M19 9l-7 7-7-7" />
                    </svg>
                  </button>

                  {/* 드롭다운 메뉴 팝오버 */}
                  {isUserMenuOpen && (
                    <>
                      <div className="absolute right-0 top-10 mt-2 w-52 rounded-2xl bg-zinc-900/95 backdrop-blur-xl border border-zinc-800 shadow-2xl p-2 z-50 animate-in fade-in slide-in-from-top-2 duration-150">
                        {/* 계정 정보 */}
                        <div className="px-3 py-2 border-b border-zinc-800/60 mb-1.5">
                          <p className="text-[11px] text-zinc-500 font-bold uppercase tracking-wider">User Account</p>
                          <p className="text-xs text-white font-bold truncate mt-0.5">{username}</p>
                        </div>

                        {/* 실시간 상태 정보 */}
                        <div className="px-3 py-1.5 space-y-1 text-[11px] text-zinc-400">
                          <div className="flex justify-between items-center">
                            <span>엔진 모드:</span>
                            <span className="font-semibold text-zinc-200">
                              {tradeMode === 'REAL' ? '🔥 REAL' : tradeMode === 'MOCK' ? '⚡ MOCK' : '📝 SIMULATED'}
                            </span>
                          </div>
                          <div className="flex justify-between items-center">
                            <span>봇 상태:</span>
                            <span className={cn("font-bold flex items-center gap-1", isBotRunning ? "text-emerald-400" : "text-zinc-500")}>
                              <span className={cn("w-1.5 h-1.5 rounded-full", isBotRunning ? "bg-emerald-500 animate-pulse" : "bg-zinc-500")}></span>
                              {isBotRunning ? "가동 중" : "정지됨"}
                            </span>
                          </div>
                        </div>

                        {/* 원클릭 퀵 봇 제어 버튼 */}
                        <div className="px-2 py-1.5">
                          <button
                            onClick={handleToggleBot}
                            disabled={isTogglingBot}
                            className={cn(
                              "w-full py-2 rounded-xl font-bold text-[11px] transition-all flex items-center justify-center gap-1.5 cursor-pointer active:scale-[0.98]",
                              isBotRunning
                                ? "bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20"
                                : "bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/20"
                            )}
                          >
                            {isTogglingBot ? (
                              <span className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin"></span>
                            ) : isBotRunning ? (
                              <>
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zM7 8a1 1 0 012 0v4a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v4a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd"/></svg>
                                <span>자동매매 즉시 정지</span>
                              </>
                            ) : (
                              <>
                                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd"/></svg>
                                <span>자동매매 즉시 가동</span>
                              </>
                            )}
                          </button>
                        </div>

                        <div className="border-t border-zinc-800/60 my-1"></div>

                        {/* 어드민 패널 단축 링크 (어드민 전용) */}
                        {role === "ADMIN" && (
                          <>
                            <Link
                              href="/admin"
                              onClick={() => setIsUserMenuOpen(false)}
                              className="flex items-center space-x-2 px-2.5 py-2 rounded-lg text-left text-zinc-400 hover:text-white hover:bg-zinc-800/50 text-xs font-semibold transition-all duration-200 cursor-pointer"
                            >
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                              </svg>
                              <span className="text-blue-400 font-bold">🛡️ 마스터 어드민 패널</span>
                            </Link>
                            <Link
                              href="/admin/system"
                              onClick={() => setIsUserMenuOpen(false)}
                              className="flex items-center space-x-2 px-2.5 py-2 rounded-lg text-left text-zinc-400 hover:text-white hover:bg-zinc-800/50 text-xs font-semibold transition-all duration-200 cursor-pointer"
                            >
                              <Activity size={14} className="text-emerald-400" />
                              <span className="text-emerald-400 font-bold">📡 시스템 헬스 관제</span>
                            </Link>
                          </>
                        )}

                        {/* 개인 투자 설정 단축 링크 */}
                        <Link
                          href="/admin/settings"
                          onClick={() => setIsUserMenuOpen(false)}
                          className="flex items-center space-x-2 px-2.5 py-2 rounded-lg text-left text-zinc-400 hover:text-white hover:bg-zinc-800/50 text-xs font-semibold transition-all duration-200 cursor-pointer"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                          </svg>
                          <span>⚙️ 개인 투자 설정</span>
                        </Link>

                        {/* 로그아웃 */}
                        <button
                          onClick={() => {
                            setIsUserMenuOpen(false);
                            handleLogout();
                          }}
                          className="w-full flex items-center space-x-2 px-2.5 py-2 rounded-lg text-left text-zinc-400 hover:text-red-400 hover:bg-red-500/10 text-xs font-semibold transition-all duration-200 cursor-pointer"
                        >
                          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                          </svg>
                          <span>로그아웃</span>
                        </button>
                      </div>
                    </>
                  )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </nav>
  );
}
