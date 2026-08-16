"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authAPI, getApiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";
import { useTranslations } from "next-intl";

export default function SignupPage() {
  const t = useTranslations("auth");
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
      toast.error(t("signup.toast.empty_fields"));
      return;
    }

    if (username.length < 3) {
      toast.error(t("signup.toast.username_too_short"));
      return;
    }

    if (password.length < 12) {
      toast.error(t("signup.toast.password_too_short"));
      return;
    }

    if (password !== confirmPassword) {
      toast.error(t("signup.toast.password_mismatch"));
      return;
    }

    setIsLoading(true);
    try {
      const res = await authAPI.signup(username, password);
      const newToken = res.data.access_token;
      const newUsername = res.data.username;
      const newRole = res.data.role;

      setAuth(newToken, newUsername, newRole);
      toast.success(t("signup.toast.success"));
      router.push("/");
    } catch (err: unknown) {
      const errorMessage = getApiErrorMessage(err, t("signup.toast.failed"));
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
          <h2 className="text-2xl font-bold tracking-tight text-white mb-2">{t("signup.title")}</h2>
          <p className="text-xs text-zinc-400">{t("signup.subtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">{t("signup.username")}</label>
            <input
              type="text"
              name="username"
              placeholder={t("signup.username")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              className="w-full px-4 py-3 rounded-xl bg-zinc-950/80 border border-zinc-800 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all duration-200"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">{t("signup.password")}</label>
            <input
              type="password"
              name="password"
              placeholder={t("signup.password")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              className="w-full px-4 py-3 rounded-xl bg-zinc-950/80 border border-zinc-800 text-white placeholder-zinc-500 text-sm focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all duration-200"
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">{t("signup.password_confirm")}</label>
            <input
              type="password"
              name="passwordConfirm"
              placeholder={t("signup.password_confirm")}
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
            {isLoading ? t("signup.submitting") : t("signup.submit")}
          </button>
        </form>

        <div className="mt-8 text-center border-t border-zinc-800/80 pt-6">
          <p className="text-xs text-zinc-400">
            {t("signup.have_account")}{" "}
            <Link href="/login" className="text-blue-400 hover:text-blue-300 font-semibold transition-colors duration-200">
              {t("signup.login_link")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
