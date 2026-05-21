"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { AlertTriangle, Server, ShieldCheck, ShieldAlert, Key, Save, Loader2, Send } from "lucide-react";
import api from "@/lib/api";

interface UserSettings {
  trade_mode: string;
  broker_provider: string;
  kis_app_key: string;
  kis_app_secret: string;
  kis_account_no: string;
  
  // Telegram Bot Settings
  telegram_bot_token: string;
  telegram_chat_id: string;
  telegram_enabled: boolean;
}

export default function AdminSettingsPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [settings, setSettings] = useState<UserSettings>({
    trade_mode: "SIMULATED",
    broker_provider: "KIS",
    kis_app_key: "",
    kis_app_secret: "",
    kis_account_no: "",
    telegram_bot_token: "",
    telegram_chat_id: "",
    telegram_enabled: false,
  });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [showRealWarning, setShowRealWarning] = useState(false);

  // Auth Guard
  useEffect(() => {
    const token = localStorage.getItem("stockauto_token");
    if (!token) {
      router.push("/login");
    } else {
      setIsAuthenticated(true);
    }
  }, [router]);

  const fetchSettings = async () => {
    try {
      const res = await api.get("/admin/");
      const data = res.data;
      setSettings({
        trade_mode: data.trade_mode || "SIMULATED",
        broker_provider: data.broker_provider || "KIS",
        kis_app_key: data.kis_app_key || "",
        kis_app_secret: data.kis_app_secret || "",
        kis_account_no: data.kis_account_no || "",
        telegram_bot_token: data.telegram_bot_token || "",
        telegram_chat_id: data.telegram_chat_id || "",
        telegram_enabled: data.telegram_enabled || false,
      });
    } catch (error: any) {
      toast.error(error.message || "Failed to load settings.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchSettings();
    }
  }, [isAuthenticated]);

  const handleSave = async (forceReal = false) => {
    if (settings.trade_mode === "REAL" && !forceReal) {
      setShowRealWarning(true);
      return;
    }
    
    setShowRealWarning(false);
    setIsSaving(true);
    
    try {
      await api.post("/admin/", settings);
      toast.success("설정이 저장되었습니다! 실시간 핫리로드 완료.");
      await fetchSettings();
    } catch (error: any) {
      toast.error(error.message || "설정 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading || !isAuthenticated) {
    return (
      <div className="min-h-[calc(100vh-4rem)] bg-zinc-950 text-white flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-white font-sans">
      <div className="max-w-4xl mx-auto p-6 mt-6">
        <div className="mb-8">
          <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400 mb-2">
            System Administration
          </h1>
          <p className="text-zinc-400 text-sm">개인 트레이딩 엔진 설정 및 증권사 API Key, 텔레그램 연동 정보를 관리합니다.</p>
        </div>

        {/* Trade Mode Selection */}
        <div className="backdrop-blur-xl bg-zinc-900/30 rounded-2xl border border-zinc-800 p-6 mb-6 shadow-lg">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Server className="w-5 h-5 text-blue-400" />
            Trading Mode
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* SIMULATED */}
            <div 
              onClick={() => setSettings({ ...settings, trade_mode: "SIMULATED" })}
              className={`p-4 rounded-xl border cursor-pointer transition-all ${
                settings.trade_mode === "SIMULATED" 
                  ? "border-blue-500 bg-blue-500/10" 
                  : "border-zinc-800 hover:border-zinc-700 bg-zinc-950/50"
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-blue-400">SIMULATED</span>
                <ShieldCheck className="w-5 h-5 text-blue-400" />
              </div>
              <p className="text-xs text-zinc-400 leading-relaxed">Paper trading using live data. Safe. No API keys required.</p>
            </div>

            {/* MOCK */}
            <div 
              onClick={() => setSettings({ ...settings, trade_mode: "MOCK" })}
              className={`p-4 rounded-xl border cursor-pointer transition-all ${
                settings.trade_mode === "MOCK" 
                  ? "border-amber-500 bg-amber-500/10" 
                  : "border-zinc-800 hover:border-zinc-700 bg-zinc-950/50"
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-amber-400">MOCK</span>
                <Server className="w-5 h-5 text-amber-400" />
              </div>
              <p className="text-xs text-zinc-400 leading-relaxed">Virtual trading via broker&apos;s mock server. Requires Mock API keys.</p>
            </div>

            {/* REAL */}
            <div 
              onClick={() => setSettings({ ...settings, trade_mode: "REAL" })}
              className={`p-4 rounded-xl border cursor-pointer transition-all ${
                settings.trade_mode === "REAL" 
                  ? "border-red-500 bg-red-500/10" 
                  : "border-zinc-800 hover:border-zinc-700 bg-zinc-950/50"
              }`}
            >
              <div className="flex justify-between items-start mb-2">
                <span className="font-bold text-red-500">REAL</span>
                <ShieldAlert className="w-5 h-5 text-red-500" />
              </div>
              <p className="text-xs text-zinc-400 leading-relaxed">Live trading with real money. Requires valid Real API keys.</p>
            </div>
          </div>
        </div>

        {/* API Credentials */}
        <div className="backdrop-blur-xl bg-zinc-900/30 rounded-2xl border border-zinc-800 p-6 mb-6 shadow-lg">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Key className="w-5 h-5 text-amber-400" />
            Broker Configuration
          </h2>
          
          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-zinc-300 mb-1">Provider</label>
              <select 
                value={settings.broker_provider}
                onChange={(e) => setSettings({ ...settings, broker_provider: e.target.value })}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 outline-none text-sm transition-all"
              >
                <option value="KIS">Korea Investment & Securities (KIS)</option>
                <option value="TOSS" disabled>Toss Securities (Coming Soon)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-300 mb-1">APP KEY</label>
              <input 
                type="text" 
                value={settings.kis_app_key || ""}
                onChange={(e) => setSettings({ ...settings, kis_app_key: e.target.value })}
                placeholder="Enter your API Key"
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 outline-none font-mono text-sm transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-300 mb-1">APP SECRET</label>
              <input 
                type="password" 
                value={settings.kis_app_secret || ""}
                onChange={(e) => setSettings({ ...settings, kis_app_secret: e.target.value })}
                placeholder="Enter your API Secret"
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 outline-none font-mono text-sm transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-zinc-300 mb-1">ACCOUNT NO</label>
              <input 
                type="text" 
                value={settings.kis_account_no || ""}
                onChange={(e) => setSettings({ ...settings, kis_account_no: e.target.value })}
                placeholder="e.g. 12345678-01"
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 outline-none font-mono text-sm transition-all"
              />
            </div>
          </div>
        </div>

        {/* Telegram Configuration */}
        <div className="backdrop-blur-xl bg-zinc-900/30 rounded-2xl border border-zinc-800 p-6 mb-6 shadow-lg">
          <div className="flex justify-between items-center mb-6 border-b border-zinc-800/80 pb-4">
            <div className="flex items-center gap-2">
              <Send className="w-5 h-5 text-indigo-400" />
              <h2 className="text-lg font-semibold">Telegram Bridge</h2>
            </div>
            <label className="relative inline-flex items-center cursor-pointer select-none">
              <input 
                type="checkbox" 
                checked={settings.telegram_enabled} 
                onChange={(e) => setSettings({ ...settings, telegram_enabled: e.target.checked })}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-zinc-500 after:border-zinc-500 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-indigo-500"></div>
              <span className="ml-3 text-xs font-semibold text-zinc-300">알림 연동 활성화</span>
            </label>
          </div>
          
          <div className="space-y-5">
            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-xs font-semibold text-zinc-300">BOT TOKEN</label>
                <span className="text-[9px] text-zinc-500 font-mono">TELEGRAM_BOT_TOKEN</span>
              </div>
              <input 
                type="password" 
                value={settings.telegram_bot_token || ""}
                onChange={(e) => setSettings({ ...settings, telegram_bot_token: e.target.value })}
                placeholder="봇 토큰 입력 (예: 123456789:ABCdef...)"
                disabled={!settings.telegram_enabled}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-white focus:ring-1 focus:ring-indigo-500 outline-none font-mono text-sm disabled:opacity-40 transition-all"
              />
            </div>

            <div>
              <div className="flex justify-between items-center mb-1.5">
                <label className="block text-xs font-semibold text-zinc-300">CHAT ID</label>
                <span className="text-[9px] text-zinc-500 font-mono">TELEGRAM_CHAT_ID</span>
              </div>
              <input 
                type="text" 
                value={settings.telegram_chat_id || ""}
                onChange={(e) => setSettings({ ...settings, telegram_chat_id: e.target.value })}
                placeholder="챗 ID 입력 (예: 987654321)"
                disabled={!settings.telegram_enabled}
                className="w-full bg-zinc-950 border border-zinc-800 rounded-xl p-3 text-white focus:ring-1 focus:ring-indigo-500 outline-none font-mono text-sm disabled:opacity-40 transition-all"
              />
              <p className="text-[11px] text-zinc-500 mt-2 leading-relaxed">
                ℹ️ 등록된 챗 ID 소유자에게만 `/status`(계좌 잔고 조회), `/stop`(봇 정지), `/run`(봇 재개) 명령어가 승인되며, 자동 매수/매도 내역이 실시간으로 비동기 전송됩니다.
              </p>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex justify-end gap-4">
          <button 
            onClick={() => handleSave(false)}
            disabled={isSaving}
            className="bg-gradient-to-r from-blue-600 to-emerald-600 hover:from-blue-500 hover:to-emerald-500 text-white font-semibold py-3 px-6 rounded-xl transition-all flex items-center gap-2 disabled:opacity-50 active:scale-[0.98]"
          >
            {isSaving ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
            Save & Hot Reload
          </button>
        </div>
      </div>

      {/* Real Mode Warning Modal */}
      {showRealWarning && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <div className="bg-zinc-900 border border-red-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <div className="flex items-center gap-3 mb-4 text-red-500">
              <AlertTriangle className="w-8 h-8" />
              <h3 className="text-xl font-bold">DANGER: REAL MODE</h3>
            </div>
            <p className="text-zinc-300 text-sm leading-relaxed mb-6">
              실전 거래(<strong className="text-red-400">REAL</strong>) 모드로 설정을 변경하려고 합니다. 
              이 모드에서는 입력하신 API Key를 바탕으로 <strong className="text-red-400">실제 금액(진짜 돈)</strong>으로 매매가 체결됩니다.
              계속 진행하시겠습니까?
            </p>
            <div className="flex justify-end gap-3 text-sm">
              <button 
                onClick={() => setShowRealWarning(false)}
                className="px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white rounded-xl transition-colors font-medium"
              >
                취소
              </button>
              <button 
                onClick={() => handleSave(true)}
                className="px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors font-semibold"
              >
                예, 실전거래 활성화
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
