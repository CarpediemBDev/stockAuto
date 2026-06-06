"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authAPI } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";

export default function SignupPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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
    if (!username || !password || !confirmPassword) {
      toast.error("모든 빈칸을 채워주세요.");
      return;
    }

    if (username.length < 3) {
      toast.error("아이디는 최소 3글자 이상이어야 합니다.");
      return;
    }

    if (password.length < 4) {
      toast.error("비밀번호는 최소 4글자 이상이어야 합니다.");
      return;
    }

    if (password !== confirmPassword) {
      toast.error("비밀번호가 서로 일치하지 않습니다.");
      return;
    }

    setIsLoading(true);
    try {
      const res = await authAPI.signup(username, password);
      const newToken = res.data.access_token;
      const newUsername = res.data.username;

      setAuth(newToken, newUsername);
      toast.success("회원가입이 완료되었으며, 성공적으로 로그인되었습니다!");
      router.push("/");
    } catch (err: unknown) {
      const errorMessage = err instanceof Error ? err.message : "회원가입에 실패했습니다. 다시 시도해 주세요.";
      toast.error(errorMessage);
    } finally {
      setIsLoading(false);
    }

  };

  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center px-4 bg-gradient-to-b from-black via-zinc-950 to-black">
      {/* 백그라운드 오라 글로우 효과 */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl -z-10" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl -z-10" />

      <div className="w-full max-w-md p-8 rounded-2xl backdrop-blur-xl bg-zinc-900/30 border border-zinc-800 shadow-2xl transition-all duration-300 hover:border-zinc-700/50">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-500 to-blue-500 flex items-center justify-center font-bold text-white text-xl shadow-lg shadow-emerald-500/20 mb-4 animate-pulse">
            SA
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-white mb-2">StockAuto 회원가입</h2>
          <p className="text-xs text-zinc-400">간편하게 회원가입 후 퀀트 자동매매를 시작하세요</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">아이디 (3글자 이상)</label>
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
            <label className="text-xs font-semibold text-zinc-300 block">비밀번호 (4글자 이상)</label>
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              className="w-full px-4 py-3 rounded-xl bg-zinc-950/80 border border-zinc-800 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all duration-200"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">비밀번호 확인</label>
            <input
              type="password"
              placeholder="Confirm Password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isLoading}
              className="w-full px-4 py-3 rounded-xl bg-zinc-950/80 border border-zinc-800 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all duration-200"
            />
          </div>

          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 rounded-xl bg-gradient-to-r from-emerald-600 to-blue-600 hover:from-emerald-500 hover:to-blue-500 text-white font-semibold text-sm shadow-lg shadow-emerald-500/10 hover:shadow-emerald-500/20 active:scale-[0.98] transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none mt-6"
          >
            {isLoading ? "가입 처리 중..." : "회원가입"}
          </button>
        </form>

        <div className="mt-8 text-center border-t border-zinc-800/80 pt-6">
          <p className="text-xs text-zinc-400">
            이미 계정이 있으신가요?{" "}
            <Link href="/login" className="text-blue-400 hover:text-blue-300 font-semibold transition-colors duration-200">
              로그인하기
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
