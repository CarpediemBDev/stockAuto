"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import {
  Globe,
  Key,
  Users,
  ShieldAlert,
  Loader2,
  HelpCircle,
  Trophy,
  SlidersHorizontal
} from "lucide-react";
import { TranslationManager } from "@/components/admin/TranslationManager";
import { UserManagement } from "@/components/admin/UserManagement";
import { SystemHealth } from "@/components/admin/SystemHealth";
import { BacktestTournament } from "@/components/admin/BacktestTournament";
import { SystemSettings } from "@/components/admin/SystemSettings";
import { useTranslations } from "next-intl";

export default function AdminPage() {
  const t = useTranslations("admin_ui");
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<string>("translation");
  const { isAuthenticated, isInitialized, role } = useAuthStore();
  const isAdmin = isAuthenticated && role === "ADMIN";

  useEffect(() => {
    if (isInitialized) {
      if (!isAuthenticated) {
        router.push("/login");
      } else if (!isAdmin) {
        router.push("/");
      }
    }
  }, [isInitialized, isAuthenticated, isAdmin, router]);

  const menuItems = [
    { id: "users", label: t("panel.menu_users"), icon: Users, enabled: true },
    { id: "translation", label: t("panel.menu_translation"), icon: Globe, enabled: true },
    { id: "runtime_settings", label: t("panel.menu_runtime"), icon: SlidersHorizontal, enabled: true },
    { id: "system", label: t("panel.menu_system"), icon: ShieldAlert, enabled: true },
    { id: "backtest", label: t("panel.menu_backtest"), icon: Trophy, enabled: true },
    { id: "access_logs", label: t("panel.menu_access_logs"), icon: Key, enabled: false },
  ];

  if (!isInitialized || !isAuthenticated || !isAdmin) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-[#090d16] text-white flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-[1400px] mx-auto">

        <div className="mb-8 border-b border-zinc-800 pb-5">
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-zinc-200 via-slate-100 to-zinc-400 bg-clip-text text-transparent">
            {t("panel.title")}
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            {t("panel.subtitle")}
          </p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">

          {/* 사이드바 메뉴 */}
          <div className="space-y-2 lg:col-span-1">
            <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-4 space-y-1.5 shadow-xl">
              <span className="text-[10px] uppercase font-bold tracking-wider text-zinc-500 px-3 mb-2 block">
                Menu Directories
              </span>

              {menuItems.map((item) => {
                const IconComponent = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={() => item.enabled && setActiveTab(item.id)}
                    disabled={!item.enabled}
                    className={`w-full flex items-center justify-between px-4 py-3 rounded-xl text-sm font-semibold transition-all duration-300 group
                      ${!item.enabled
                        ? "text-zinc-600 cursor-not-allowed bg-transparent"
                        : activeTab === item.id
                          ? "bg-zinc-800 text-white shadow-lg border border-zinc-700/50"
                          : "text-zinc-400 hover:text-slate-100 hover:bg-zinc-800/30"
                      }`}
                  >
                    <div className="flex items-center gap-3">
                      <IconComponent size={18} className={activeTab === item.id ? "text-blue-400" : "text-zinc-500"} />
                      <span>{item.label}</span>
                    </div>
                    {!item.enabled && (
                      <span className="text-[9px] bg-zinc-800/40 text-zinc-600 px-1.5 py-0.5 rounded border border-zinc-800/20 font-bold group-hover:text-blue-500 group-hover:border-blue-500/20 transition-all">
                        SOON
                      </span>
                    )}
                  </button>
                );
              })}
            </div>

            <div className="bg-gradient-to-br from-blue-950/20 to-zinc-900/40 rounded-2xl border border-blue-900/20 p-5 space-y-3 shadow-md">
              <div className="flex items-center gap-2 text-blue-400">
                <HelpCircle size={18} />
                <span className="text-xs font-bold uppercase tracking-wider">Admin Guide</span>
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                {t("panel.notice_master_only_pre")}<strong>{t("panel.notice_master_only_strong")}</strong>{t("panel.notice_master_only_post")}
              </p>
            </div>
          </div>

          {/* 메인 콘텐츠 패널 */}
          <div className="lg:col-span-3 space-y-6 min-w-0">
            {activeTab === "translation" && <TranslationManager />}
            {activeTab === "users" && <UserManagement />}
            {activeTab === "runtime_settings" && <SystemSettings />}
            {activeTab === "system" && <SystemHealth />}
            {activeTab === "backtest" && <BacktestTournament />}

            {activeTab !== "translation" && activeTab !== "users" && activeTab !== "runtime_settings" && activeTab !== "system" && activeTab !== "backtest" && (
              <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-12 text-center shadow-xl">
                <Loader2 size={48} className="mx-auto text-zinc-600 mb-4 animate-pulse" />
                <h3 className="text-lg font-bold text-slate-300">{t("panel.coming_soon_title")}</h3>
                <p className="text-sm text-zinc-500 mt-2">
                  {t("panel.coming_soon_body", { label: menuItems.find(m => m.id === activeTab)?.label ?? "" })}
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
