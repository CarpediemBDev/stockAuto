"use client";

import React, { startTransition, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/store/authStore";
import { toast } from "sonner";
import {
  AlertTriangle,
  Ban,
  Key,
  Loader2,
  RefreshCw,
  Save,
  Send,
  Server,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import api from "@/lib/api";

type SubTab = "environment" | "telegram" | "danger";
type TradeMode = "SIMULATED" | "MOCK" | "REAL";

interface UserSettings {
  trade_mode: TradeMode;
  broker_provider: string;
  telegram_chat_id: string;
  telegram_enabled: boolean;
  global_bot_username?: string;
  has_kis_credentials: boolean;
  kis_account_no_masked?: string | null;
  kis_verification_status?: string;
  kis_verified_trade_mode?: string | null;
  kis_verified_at?: string | null;
  kis_credential_error?: string | null;
}

interface KisCredentialForm {
  kis_app_key: string;
  kis_app_secret: string;
  kis_account_no: string;
}

const EMPTY_KIS_FORM: KisCredentialForm = {
  kis_app_key: "",
  kis_app_secret: "",
  kis_account_no: "",
};

const DEFAULT_SETTINGS: UserSettings = {
  trade_mode: "SIMULATED",
  broker_provider: "KIS",
  telegram_chat_id: "",
  telegram_enabled: false,
  global_bot_username: "",
  has_kis_credentials: false,
  kis_account_no_masked: null,
  kis_verification_status: "unverified",
  kis_verified_trade_mode: null,
  kis_verified_at: null,
  kis_credential_error: null,
};

function normalizeTradeMode(value: unknown): TradeMode {
  if (value === "MOCK" || value === "REAL") {
    return value;
  }
  return "SIMULATED";
}

export default function PersonalSettingsPage() {
  const router = useRouter();
  const { isAuthenticated, isInitialized, username: storedUsername } = useAuthStore();
  const [dbSettings, setDbSettings] = useState<UserSettings>(DEFAULT_SETTINGS);
  const [kisForm, setKisForm] = useState<KisCredentialForm>(EMPTY_KIS_FORM);
  const [username, setUsername] = useState<string>("");
  const [subTab, setSubTab] = useState<SubTab>("environment");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isCredentialSaving, setIsCredentialSaving] = useState(false);
  const [isCredentialDeleting, setIsCredentialDeleting] = useState(false);
  const [showRealWarning, setShowRealWarning] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);
  const [showLiquidateModal, setShowLiquidateModal] = useState(false);
  const [isDangerActionLoading, setIsDangerActionLoading] = useState(false);

  useEffect(() => {
    if (isInitialized) {
      if (!isAuthenticated) {
        router.push("/login");
        return;
      }

      startTransition(() => {
        setUsername(storedUsername || "");
      });
    }
  }, [isInitialized, isAuthenticated, storedUsername, router]);

  const applySettings = useCallback((data: Partial<UserSettings>) => {
    setDbSettings({
      trade_mode: normalizeTradeMode(data.trade_mode),
      broker_provider: data.broker_provider || "KIS",
      telegram_chat_id: data.telegram_chat_id || "",
      telegram_enabled: Boolean(data.telegram_enabled),
      global_bot_username: data.global_bot_username || "stockauto_official_bot",
      has_kis_credentials: Boolean(data.has_kis_credentials),
      kis_account_no_masked: data.kis_account_no_masked || null,
      kis_verification_status: data.kis_verification_status || "unverified",
      kis_verified_trade_mode: data.kis_verified_trade_mode || null,
      kis_verified_at: data.kis_verified_at || null,
      kis_credential_error: data.kis_credential_error || null,
    });
    setKisForm(EMPTY_KIS_FORM);
  }, []);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await api.get("/admin/");
      applySettings(res.data);
    } catch (err) {
      const error = err as Error;
      toast.error(error.message || "설정을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [applySettings]);

  useEffect(() => {
    if (!isAuthenticated) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSettings();
  }, [isAuthenticated, fetchSettings]);

  const isKisMode = dbSettings.trade_mode === "MOCK" || dbSettings.trade_mode === "REAL";
  const isVerifiedForSelectedMode = useMemo(
    () =>
      dbSettings.has_kis_credentials &&
      dbSettings.kis_verification_status === "verified" &&
      dbSettings.kis_verified_trade_mode === dbSettings.trade_mode,
    [
      dbSettings.has_kis_credentials,
      dbSettings.kis_verification_status,
      dbSettings.kis_verified_trade_mode,
      dbSettings.trade_mode,
    ]
  );

  const credentialStatusLabel = useMemo(() => {
    if (dbSettings.kis_verification_status === "crypto_error") return "복호화 오류";
    if (isVerifiedForSelectedMode) return "검증 완료";
    if (dbSettings.has_kis_credentials) return "재검증 필요";
    return "미저장";
  }, [dbSettings.has_kis_credentials, dbSettings.kis_verification_status, isVerifiedForSelectedMode]);

  const handleVerifyAndSaveKisCredentials = async () => {
    if (!isKisMode) {
      toast.info("SIMULATED 모드는 KIS 인증정보가 필요하지 않습니다.");
      return;
    }

    if (!kisForm.kis_app_key.trim() || !kisForm.kis_app_secret.trim() || !kisForm.kis_account_no.trim()) {
      toast.error("APP KEY, APP SECRET, ACCOUNT NO를 모두 입력하세요.");
      return;
    }

    setIsCredentialSaving(true);
    try {
      const res = await api.post("/admin/kis-credentials/verify-and-save", {
        trade_mode: dbSettings.trade_mode,
        ...kisForm,
      });
      if (res.data?.settings) {
        applySettings(res.data.settings);
      } else {
        await fetchSettings();
      }
      toast.success(res.data?.message || "KIS 인증정보가 검증 및 저장되었습니다.");
    } catch (err) {
      toast.error((err as Error).message || "KIS 인증정보 검증 및 저장에 실패했습니다.");
    } finally {
      setIsCredentialSaving(false);
    }
  };

  const handleDeleteKisCredentials = async () => {
    setIsCredentialDeleting(true);
    try {
      const res = await api.delete("/admin/kis-credentials");
      if (res.data?.settings) {
        applySettings(res.data.settings);
      } else {
        await fetchSettings();
      }
      toast.success("KIS 인증정보가 삭제되었습니다.");
    } catch (err) {
      toast.error((err as Error).message || "KIS 인증정보 삭제에 실패했습니다.");
    } finally {
      setIsCredentialDeleting(false);
    }
  };

  const handleSave = async (forceReal = false) => {
    if (dbSettings.trade_mode === "REAL" && !forceReal) {
      setShowRealWarning(true);
      return;
    }

    if (isKisMode && !isVerifiedForSelectedMode) {
      toast.error(`${dbSettings.trade_mode} 모드를 저장하려면 KIS 인증정보를 먼저 검증 및 저장하세요.`);
      return;
    }

    setShowRealWarning(false);
    setIsSaving(true);

    try {
      const res = await api.post("/admin/", {
        trade_mode: dbSettings.trade_mode,
        broker_provider: dbSettings.broker_provider,
        telegram_chat_id: dbSettings.telegram_chat_id,
        telegram_enabled: dbSettings.telegram_enabled,
      });
      applySettings(res.data);
      toast.success("설정이 저장되었습니다.");
    } catch (err) {
      toast.error((err as Error).message || "설정 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  const handleResetBalance = async () => {
    setIsDangerActionLoading(true);
    try {
      await api.post("/account/reset-balance");
      toast.success("가상 계좌 자산과 로그를 초기화했습니다.");
      setShowResetModal(false);
      await fetchSettings();
    } catch (err) {
      toast.error((err as Error).message || "계좌 초기화에 실패했습니다.");
    } finally {
      setIsDangerActionLoading(false);
    }
  };

  const handleForceLiquidate = async () => {
    setIsDangerActionLoading(true);
    try {
      const res = await api.post("/account/force-liquidate");
      toast.success(res.data.message || "보유 주식을 전량 청산했습니다.");
      setShowLiquidateModal(false);
    } catch (err) {
      toast.error((err as Error).message || "강제 청산 중 오류가 발생했습니다.");
    } finally {
      setIsDangerActionLoading(false);
    }
  };

  const modeCards: Array<{
    id: TradeMode;
    label: string;
    color: string;
    icon: typeof ShieldCheck;
    body: string;
  }> = [
    {
      id: "SIMULATED",
      label: "SIMULATED",
      color: "text-blue-400 border-blue-500 bg-blue-500/5",
      icon: ShieldCheck,
      body: "실시간 가격 기반 가상 투자 모드",
    },
    {
      id: "MOCK",
      label: "MOCK",
      color: "text-amber-400 border-amber-500 bg-amber-500/5",
      icon: Server,
      body: "KIS 모의투자 서버 연동 모드",
    },
    {
      id: "REAL",
      label: "REAL",
      color: "text-red-400 border-red-500 bg-red-500/5",
      icon: ShieldAlert,
      body: "실전 계좌 기반 자동매매 모드",
    },
  ];

  if (isLoading || !isInitialized || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-zinc-950 text-white flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white font-sans">
      <div className="max-w-4xl mx-auto p-6 mt-6">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-zinc-800 pb-4 mb-8 gap-4">
          <div>
            <h1 className="text-2xl font-extrabold text-zinc-100 mb-1">개인 투자 설정</h1>
            <p className="text-zinc-400 text-xs">트레이딩 모드, 증권사 연동, 텔레그램 연결을 관리합니다.</p>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-8 items-start">
          <div className="w-full md:w-48 shrink-0 flex flex-row md:flex-col gap-1 bg-zinc-950 md:bg-transparent pb-3 md:pb-0 border-b md:border-b-0 border-zinc-900 overflow-x-auto md:overflow-x-visible">
            {[
              { id: "environment", label: "Trading", icon: Server, color: "text-blue-400" },
              { id: "telegram", label: "Telegram", icon: Send, color: "text-indigo-400" },
              { id: "danger", label: "Danger", icon: AlertTriangle, color: "text-red-500" },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = subTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setSubTab(item.id as SubTab)}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs font-bold transition-all text-left w-full cursor-pointer whitespace-nowrap ${
                    isActive ? "bg-zinc-900 text-white" : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40"
                  }`}
                >
                  <Icon className={`w-3.5 h-3.5 ${isActive ? item.color : "text-zinc-500"}`} />
                  {item.label}
                </button>
              );
            })}
          </div>

          <div className="flex-1 min-w-0 w-full">
            {subTab === "environment" && (
              <div className="space-y-8">
                <div className="space-y-4">
                  <div className="flex flex-col gap-1.5 pb-3 border-b border-zinc-900">
                    <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                      <Server className="w-4 h-4 text-blue-400" />
                      Trading Mode
                    </h2>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {modeCards.map((mode) => {
                      const Icon = mode.icon;
                      const isActive = dbSettings.trade_mode === mode.id;
                      return (
                        <button
                          key={mode.id}
                          onClick={() => setDbSettings((prev) => ({ ...prev, trade_mode: mode.id }))}
                          className={`p-4 rounded-lg border text-left cursor-pointer transition-all ${
                            isActive ? mode.color : "border-zinc-900 bg-zinc-900/10 hover:border-zinc-800"
                          }`}
                        >
                          <div className="flex justify-between items-start mb-2">
                            <span className="font-bold text-xs">{mode.label}</span>
                            <Icon className="w-4 h-4" />
                          </div>
                          <p className="text-[10px] text-zinc-500 leading-relaxed">{mode.body}</p>
                        </button>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-4 pt-6 border-t border-zinc-900">
                  <div className="flex flex-col gap-1.5 pb-2">
                    <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                      <Key className="w-4 h-4 text-amber-400" />
                      Broker Config
                    </h2>
                  </div>

                  {dbSettings.trade_mode === "SIMULATED" ? (
                    <div className="p-4 rounded-lg border border-blue-500/20 bg-blue-500/5 flex items-center gap-3">
                      <ShieldCheck className="w-5 h-5 text-blue-400 shrink-0" />
                      <p className="text-[11px] text-zinc-400 leading-relaxed">
                        SIMULATED 모드에서는 KIS 인증정보를 사용하지 않습니다.
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-4 animate-in fade-in slide-in-from-top-1 duration-300">
                      <div>
                        <label className="block text-xs font-semibold text-zinc-400 mb-1.5">Provider</label>
                        <select
                          value={dbSettings.broker_provider}
                          onChange={(e) => setDbSettings((prev) => ({ ...prev, broker_provider: e.target.value }))}
                          className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none text-xs transition-all"
                        >
                          <option value="KIS">Korea Investment & Securities (KIS)</option>
                          <option value="TOSS" disabled>
                            Toss Securities (Coming Soon)
                          </option>
                        </select>
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-4 gap-2">
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">저장 상태</p>
                          <p className="text-xs font-bold text-zinc-200">
                            {dbSettings.has_kis_credentials ? "저장됨" : "없음"}
                          </p>
                        </div>
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">검증 상태</p>
                          <p className={`text-xs font-bold ${isVerifiedForSelectedMode ? "text-emerald-400" : "text-amber-400"}`}>
                            {credentialStatusLabel}
                          </p>
                        </div>
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">검증 모드</p>
                          <p className="text-xs font-bold text-zinc-200">{dbSettings.kis_verified_trade_mode || "-"}</p>
                        </div>
                        <div className="rounded-lg border border-zinc-900 bg-zinc-900/20 p-3">
                          <p className="text-[10px] text-zinc-500 mb-1">계좌</p>
                          <p className="text-xs font-bold text-zinc-200 font-mono">
                            {dbSettings.kis_account_no_masked || "-"}
                          </p>
                        </div>
                      </div>

                      {dbSettings.kis_credential_error && (
                        <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-300">
                          {dbSettings.kis_credential_error}
                        </div>
                      )}

                      <div className="grid grid-cols-1 gap-3">
                        <div>
                          <label className="block text-xs font-semibold text-zinc-400 mb-1.5">APP KEY</label>
                          <input
                            type="text"
                            value={kisForm.kis_app_key}
                            onChange={(e) => setKisForm((prev) => ({ ...prev, kis_app_key: e.target.value }))}
                            placeholder={dbSettings.has_kis_credentials ? "•••••••••••••••• (새로 입력 시 덮어쓰기)" : "Enter APP KEY"}
                            className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                            autoComplete="off"
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-zinc-400 mb-1.5">APP SECRET</label>
                          <input
                            type="password"
                            value={kisForm.kis_app_secret}
                            onChange={(e) => setKisForm((prev) => ({ ...prev, kis_app_secret: e.target.value }))}
                            placeholder={dbSettings.has_kis_credentials ? "•••••••••••••••• (새로 입력 시 덮어쓰기)" : "Enter APP SECRET"}
                            className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                            autoComplete="new-password"
                          />
                        </div>

                        <div>
                          <label className="block text-xs font-semibold text-zinc-400 mb-1.5">ACCOUNT NO</label>
                          <input
                            type="text"
                            value={kisForm.kis_account_no}
                            onChange={(e) => setKisForm((prev) => ({ ...prev, kis_account_no: e.target.value }))}
                            placeholder={dbSettings.has_kis_credentials ? `${dbSettings.kis_account_no_masked || "••••••••"} (새로 입력 시 덮어쓰기)` : "12345678-01"}
                            className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                            autoComplete="off"
                          />
                        </div>
                      </div>

                      <div className="flex flex-col sm:flex-row gap-2 justify-end">
                        {dbSettings.has_kis_credentials && (
                          <button
                            type="button"
                            onClick={handleDeleteKisCredentials}
                            disabled={isCredentialDeleting || isCredentialSaving}
                            className="border border-red-500/40 text-red-300 hover:bg-red-500/10 disabled:opacity-50 px-4 py-2.5 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer"
                          >
                            {isCredentialDeleting ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Trash2 className="w-3.5 h-3.5" />
                            )}
                            인증정보 삭제
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={handleVerifyAndSaveKisCredentials}
                          disabled={isCredentialSaving || isCredentialDeleting}
                          className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-4 py-2.5 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 cursor-pointer"
                        >
                          {isCredentialSaving ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <ShieldCheck className="w-3.5 h-3.5" />
                          )}
                          KIS 검증 및 저장
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex justify-end pt-6 border-t border-zinc-900">
                  <button
                    onClick={() => handleSave(false)}
                    disabled={isSaving}
                    className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-xs font-bold transition-all active:scale-95 flex items-center gap-2 cursor-pointer shadow-md shadow-blue-900/30"
                  >
                    {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    설정 저장
                  </button>
                </div>
              </div>
            )}

            {subTab === "telegram" && (
              <div className="space-y-6">
                <div className="flex flex-col gap-1.5 pb-4 border-b border-zinc-900">
                  <h2 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                    <Send className="w-4 h-4 text-indigo-400" />
                    Telegram Bridge
                  </h2>
                </div>

                <div className="space-y-4">
                  <div className="flex justify-between items-center bg-zinc-900/30 border border-zinc-900 rounded-lg p-4">
                    <span className="text-xs font-semibold text-zinc-300">텔레그램 알림 연동</span>
                    <label className="relative inline-flex items-center cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={dbSettings.telegram_enabled}
                        onChange={(e) => setDbSettings((prev) => ({ ...prev, telegram_enabled: e.target.checked }))}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-zinc-500 after:border-zinc-500 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-500"></div>
                    </label>
                  </div>

                  <div className="p-4 rounded-lg border border-indigo-500/20 bg-indigo-500/5 space-y-3">
                    <span className="text-xs font-bold text-indigo-400">1-Click 연결</span>
                    <a
                      href={
                        dbSettings.telegram_enabled && dbSettings.global_bot_username
                          ? `https://t.me/${dbSettings.global_bot_username}?start=${username}`
                          : "#"
                      }
                      onClick={(e) => {
                        if (!dbSettings.telegram_enabled) {
                          e.preventDefault();
                          toast.warning("텔레그램 연동 스위치를 먼저 켜세요.");
                        }
                      }}
                      target="_blank"
                      rel="noopener noreferrer"
                      className={`inline-flex w-full items-center justify-center gap-2 px-4 py-3 rounded-lg text-xs font-black transition-all active:scale-[0.98] shadow-md ${
                        dbSettings.telegram_enabled
                          ? "bg-indigo-600 hover:bg-indigo-500 text-white shadow-indigo-500/20"
                          : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                      }`}
                    >
                      <Send className="w-3.5 h-3.5" />
                      공식 텔레그램 연결
                    </a>
                  </div>

                  <div className="p-4 rounded-lg border border-zinc-900 bg-zinc-900/10 space-y-3">
                    <span className="text-xs font-bold text-zinc-400">수동 CHAT ID</span>
                    <input
                      type="text"
                      value={dbSettings.telegram_chat_id || ""}
                      onChange={(e) => setDbSettings((prev) => ({ ...prev, telegram_chat_id: e.target.value }))}
                      placeholder="987654321"
                      disabled={!dbSettings.telegram_enabled}
                      className="w-full bg-zinc-950 border border-zinc-900 rounded-lg p-3 text-white focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none font-mono text-xs disabled:opacity-40 transition-all"
                    />
                  </div>
                </div>

                <div className="flex justify-end pt-6 border-t border-zinc-900">
                  <button
                    onClick={() => handleSave(false)}
                    disabled={isSaving}
                    className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-lg text-xs font-bold transition-all flex items-center gap-2 cursor-pointer"
                  >
                    {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    저장
                  </button>
                </div>
              </div>
            )}

            {subTab === "danger" && (
              <div className="space-y-6">
                <div className="flex flex-col gap-1.5 pb-4 border-b border-zinc-900">
                  <h2 className="text-base font-bold text-red-400 flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-500" />
                    Danger Zone
                  </h2>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="p-4 bg-zinc-900/20 rounded-lg border border-zinc-900 flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                        <RefreshCw className="w-3.5 h-3.5 text-zinc-400" />
                        모의투자 자산 초기화
                      </h3>
                      <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                        SIMULATED 모드의 보유 주식, 거래 기록, 행동 로그를 초기화합니다.
                      </p>
                    </div>
                    <div className="mt-4">
                      {dbSettings.trade_mode === "SIMULATED" ? (
                        <button
                          onClick={() => setShowResetModal(true)}
                          className="w-full py-2 rounded-lg bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 text-xs font-bold transition-all active:scale-[0.98] cursor-pointer"
                        >
                          가상 잔고 초기화
                        </button>
                      ) : (
                        <p className="text-[10px] text-zinc-500 text-center font-semibold italic bg-zinc-950/50 py-2 rounded-lg">
                          SIMULATED 전용
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="p-4 bg-zinc-900/20 rounded-lg border border-zinc-900 flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                        <Ban className="w-3.5 h-3.5 text-zinc-400" />
                        보유 주식 강제 청산
                      </h3>
                      <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                        현재 보유 중인 종목을 시장가 기준으로 청산합니다.
                      </p>
                    </div>
                    <div className="mt-4">
                      <button
                        onClick={() => setShowLiquidateModal(true)}
                        className="w-full py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all active:scale-[0.98] flex items-center justify-center gap-1 cursor-pointer"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        전량 청산
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {showRealWarning && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowRealWarning(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                  <ShieldAlert className="w-7 h-7 text-red-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">실전 모드 전환 확인</h3>
                <p className="text-xs text-red-300 font-semibold leading-relaxed">
                  REAL 모드는 실제 계좌 자금으로 주문을 실행할 수 있습니다.
                </p>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowRealWarning(false)}
                    className="flex-1 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    취소
                  </button>
                  <button
                    onClick={() => handleSave(true)}
                    className="flex-1 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    <ShieldAlert className="w-3.5 h-3.5" />
                    REAL 저장
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {showResetModal && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowResetModal(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-amber-500/10 flex items-center justify-center">
                  <RefreshCw className="w-7 h-7 text-amber-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">가상 잔고 초기화</h3>
                <p className="text-xs text-red-300 font-semibold leading-relaxed">이 작업은 되돌릴 수 없습니다.</p>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowResetModal(false)}
                    className="flex-1 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    취소
                  </button>
                  <button
                    onClick={handleResetBalance}
                    disabled={isDangerActionLoading}
                    className="flex-1 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    {isDangerActionLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <RefreshCw className="w-3.5 h-3.5" />
                    )}
                    초기화
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {showLiquidateModal && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowLiquidateModal(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                  <Trash2 className="w-7 h-7 text-red-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">보유 주식 전량 청산</h3>
                <p className="text-xs text-red-300 font-semibold leading-relaxed">시장가 기준으로 즉시 청산합니다.</p>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowLiquidateModal(false)}
                    className="flex-1 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    취소
                  </button>
                  <button
                    onClick={handleForceLiquidate}
                    disabled={isDangerActionLoading}
                    className="flex-1 py-2.5 rounded-lg bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    {isDangerActionLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Trash2 className="w-3.5 h-3.5" />
                    )}
                    청산 실행
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
