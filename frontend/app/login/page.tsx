"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authAPI } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const { isAuthenticated, setAuth } = useAuthStore();

  // 이미 로그인되어 있으면 대시보드로 이동
  useEffect(() => {
    if (isAuthenticated) {
      router.push("/");
    }
  }, [isAuthenticated, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) {
      toast.error("아이디와 비밀번호를 모두 입력해 주세요.");
      return;
    }

    setIsLoading(true);
    try {
      const res = await authAPI.login(username, password);
      // api.ts response interceptor가 data.data를 반환
      const newToken = res.data.access_token;
      const newUsername = res.data.username;
      const newRole = res.data.role;

      setAuth(newToken, newUsername, newRole);
      toast.success("성공적으로 로그인되었습니다!");
      router.push("/");
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "로그인에 실패했습니다. 다시 시도해 주세요.";
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }

  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4 bg-gradient-to-b from-black via-zinc-950 to-black">
      {/* 백그라운드 오라 글로우 효과 */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl -z-10" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl -z-10" />

      <div className="w-full max-w-md p-8 rounded-2xl backdrop-blur-xl bg-zinc-900/30 border border-zinc-800 shadow-2xl transition-all duration-300 hover:border-zinc-700/50">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500 flex items-center justify-center font-bold text-white text-xl shadow-lg shadow-blue-500/20 mb-4 animate-pulse">
            SA
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-white mb-2">StockAuto 로그인</h2>
          <p className="text-xs text-zinc-400">자율 트레이딩 퀀트 플랫폼에 오신 것을 환영합니다</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">아이디</label>
            <input
              type="text"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              className="w-full px-4 py-3 rounded-xl bg-zinc-950/80 border border-zinc-800 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all duration-200"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">비밀번호</label>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              className="w-full px-4 py-3 rounded-xl bg-zinc-950/80 border border-zinc-800 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all duration-200"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-blue-600 to-emerald-600 hover:from-blue-500 hover:to-emerald-500 text-white font-semibold text-sm shadow-lg shadow-blue-500/10 hover:shadow-blue-500/20 active:scale-[0.98] transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none mt-6"
          >
            {isLoading ? "로그인 중..." : "로그인"}
          </button>
        </form>

        <div className="mt-8 text-center border-t border-zinc-800/80 pt-6">
          <p className="text-xs text-zinc-400">
            아직 계정이 없으신가요?{" "}
            <Link href="/signup" className="text-blue-400 hover:text-blue-300 font-semibold transition-colors duration-200">
              무료 회원가입
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
