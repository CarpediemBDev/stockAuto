"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authAPI, getApiErrorMessage } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";
import { useTranslations } from "next-intl";
import { Button, Input } from "@/components/ui";

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
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl -z-10" />

      <div className="w-full max-w-md p-8 rounded-2xl backdrop-blur-xl bg-surface-card/80 border border-zinc-800/80 shadow-2xl transition-all duration-300 hover:border-zinc-700">
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-emerald-500 to-indigo-500 flex items-center justify-center font-bold text-white text-xl shadow-lg shadow-emerald-500/20 mb-4 animate-pulse">
            SA
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-white mb-2">{t("signup.title")}</h2>
          <p className="text-xs text-zinc-400">{t("signup.subtitle")}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">{t("signup.username")}</label>
            <Input
              type="text"
              name="username"
              placeholder={t("signup.username")}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">{t("signup.password")}</label>
            <Input
              type="password"
              name="password"
              placeholder={t("signup.password")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <div className="space-y-2">
            <label className="text-xs font-semibold text-zinc-300 block">{t("signup.password_confirm")}</label>
            <Input
              type="password"
              name="passwordConfirm"
              placeholder={t("signup.password_confirm")}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isLoading}
            />
          </div>

          <Button
            type="submit"
            isLoading={isLoading}
            className="w-full mt-6"
            size="lg"
          >
            {isLoading ? t("signup.submitting") : t("signup.submit")}
          </Button>
        </form>

        <div className="mt-8 text-center border-t border-zinc-800/80 pt-6">
          <p className="text-xs text-zinc-400">
            {t("signup.have_account")}{" "}
            <Link href="/login" className="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors duration-200">
              {t("signup.login_link")}
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
