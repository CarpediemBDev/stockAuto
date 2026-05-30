"use client";

import React, { useState, useEffect, useCallback, startTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { 
  AlertTriangle, Server, ShieldCheck, ShieldAlert, Key, Save, Loader2, Send, 
  RefreshCw, Trash2, Ban
} from "lucide-react";
import api from "@/lib/api";

interface UserSettings {
  trade_mode: string;
  broker_provider: string;
  kis_app_key: string;
  kis_app_secret: string;
  kis_account_no: string;
  telegram_chat_id: string;
  telegram_enabled: boolean;
  global_bot_username?: string;
}

export default function PersonalSettingsPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  
  const [settings, setSettings] = useState<UserSettings>({
    trade_mode: "SIMULATED",
    broker_provider: "KIS",
    kis_app_key: "",
    kis_app_secret: "",
    kis_account_no: "",
    telegram_chat_id: "",
    telegram_enabled: false,
    global_bot_username: "",
  });
  const [username, setUsername] = useState<string>("");
  const [subTab, setSubTab] = useState<"environment" | "telegram" | "danger">("environment");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [showRealWarning, setShowRealWarning] = useState(false);

  const [showResetModal, setShowResetModal] = useState(false);
  const [showLiquidateModal, setShowLiquidateModal] = useState(false);
  const [isDangerActionLoading, setIsDangerActionLoading] = useState(false);

  useEffect(() => {
    const token = localStorage.getItem("stockauto_token");
    const storedUsername = localStorage.getItem("stockauto_username");

    if (!token) {
      router.push("/login");
    } else {
      startTransition(() => {
        setIsAuthenticated(true);
        setUsername(storedUsername || "");
      });
    }
  }, [router]);

  const fetchSettings = useCallback(async () => {
    try {
      const res = await api.get("/admin/");
      const data = res.data;
      setSettings({
        trade_mode: data.trade_mode || "SIMULATED",
        broker_provider: data.broker_provider || "KIS",
        kis_app_key: data.kis_app_key || "",
        kis_app_secret: data.kis_app_secret || "",
        kis_account_no: data.kis_account_no || "",
        telegram_chat_id: data.telegram_chat_id || "",
        telegram_enabled: data.telegram_enabled || false,
        global_bot_username: data.global_bot_username || "stockauto_official_bot",
      });
    } catch (err) {
      const error = err as Error;
      toast.error(error.message || "설정을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!isAuthenticated) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSettings();
  }, [isAuthenticated, fetchSettings]);

  const handleSave = async (forceReal = false) => {
    if (settings.trade_mode === "MOCK" || settings.trade_mode === "REAL") {
      const key = settings.kis_app_key;
      const placeholderKeys = ["YOUR_APP_KEY_HERE", "your_virtual_app_key_here", "your_real_app_key_here", "your_app_key_here", "", null, undefined];
      if (placeholderKeys.includes(key)) {
        toast.error(`[저장 실패] ${settings.trade_mode} 모드를 사용하려면 'Broker Config' 탭에서 유효한 증권사 API 키를 먼저 입력해야 합니다.`);
        return;
      }
    }

    if (settings.trade_mode === "REAL" && !forceReal) {
      setShowRealWarning(true);
      return;
    }
    
    setShowRealWarning(false);
    setIsSaving(true);
    
    try {
      let verifySuccess = true;
      let verifyMessage = "";
      
      if (settings.trade_mode === "MOCK" || settings.trade_mode === "REAL") {
        try {
          const verifyRes = await api.post("/admin/verify-kis", settings);
          verifySuccess = verifyRes.data.success;
          verifyMessage = verifyRes.data.message;
        } catch (verifyErr) {
          verifySuccess = false;
          verifyMessage = (verifyErr as Error).message || "통신 검증 중 오류가 발생했습니다.";
        }
      }
      
      await api.post("/admin/", settings);
      
      if (!verifySuccess) {
        toast.warning(
          <div>
            <p className="font-bold text-amber-500">⚠️ KIS 연동 검증 실패</p>
            <p className="text-xs text-zinc-300 mt-1">{verifyMessage}</p>
            <p className="text-xs text-amber-400/90 font-semibold mt-1.5 leading-normal">
              안전을 위해 백엔드 트레이딩 엔진이 SIMULATED(모의 투자) 브로커로 자동 후퇴(대체)하여 가동됩니다.
            </p>
          </div>,
          { duration: 8000 }
        );
      } else {
        toast.success(
          settings.trade_mode === "SIMULATED"
            ? "설정이 정상적으로 저장되었습니다! 실시간 핫리로드 완료."
            : "설정이 저장되었으며 KIS API 연동이 정상 검증되었습니다!"
        );
      }
      
      await fetchSettings();
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
      toast.success("가상 계좌 자산 및 모든 로그가 성공적으로 리셋되었습니다!");
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
      toast.success(res.data.message || "보유 중인 주식이 모두 전량 청산되었습니다.");
      setShowLiquidateModal(false);
    } catch (err) {
      toast.error((err as Error).message || "일괄 청산 도중 오류가 발생했습니다.");
    } finally {
      setIsDangerActionLoading(false);
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
        
        <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-zinc-800 pb-4 mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400 mb-1">
              개인 투자 설정
            </h1>
            <p className="text-zinc-400 text-xs">
              개인 트레이딩 엔진 설정 및 증권사 API Key, 텔레그램 연동 정보를 관리합니다.
            </p>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-8 items-start">
          <div className="w-full md:w-48 shrink-0 flex flex-row md:flex-col gap-1 bg-zinc-950 md:bg-transparent pb-3 md:pb-0 border-b md:border-b-0 border-zinc-900 overflow-x-auto md:overflow-x-visible">
            {[
              { id: "environment", label: "Trading Environment", icon: Server, color: "text-blue-400" },
              { id: "telegram", label: "Telegram Bridge", icon: Send, color: "text-indigo-400" },
              { id: "danger", label: "Danger Zone", icon: AlertTriangle, color: "text-red-500" },
            ].map((item) => {
              const Icon = item.icon;
              const isActive = subTab === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => setSubTab(item.id as "environment" | "telegram" | "danger")}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-xs font-bold transition-all text-left w-full cursor-pointer whitespace-nowrap ${
                    isActive 
                      ? "bg-zinc-900 text-white shadow-inner" 
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900/40"
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
                {/* 섹션 1. 투자 구동 모드 선택 */}
                <div className="space-y-4">
                  <div className="flex flex-col gap-1.5 pb-3 border-b border-zinc-900">
                    <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                      <Server className="w-4 h-4 text-blue-400" />
                      1단계: 투자 구동 모드 선택 (Trading Mode)
                    </h2>
                    <p className="text-[11px] text-zinc-400 leading-relaxed">
                      자동매매 엔진의 구동 환경을 지정합니다. Simulated 모드는 API Key 검증 없이 즉시 가상 모의 투자를 체험할 수 있는 가장 안전한 모드입니다.
                    </p>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div 
                      onClick={() => setSettings({ ...settings, trade_mode: "SIMULATED" })}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        settings.trade_mode === "SIMULATED" 
                          ? "border-blue-500 bg-blue-500/5 shadow-[0_0_15px_rgba(59,130,246,0.1)]" 
                          : "border-zinc-900 bg-zinc-900/10 hover:border-zinc-800 hover:bg-zinc-900/20"
                      }`}
                    >
                      <div className="flex justify-between items-start mb-2">
                        <span className="font-bold text-xs text-blue-400">SIMULATED</span>
                        <ShieldCheck className="w-4 h-4 text-blue-400" />
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-relaxed">
                        실시간 시장 가격 기반 가상 투자. API 키 불필요. 안전한 테스트용 모드.
                      </p>
                    </div>

                    <div 
                      onClick={() => setSettings({ ...settings, trade_mode: "MOCK" })}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        settings.trade_mode === "MOCK" 
                          ? "border-amber-500 bg-amber-500/5 shadow-[0_0_15px_rgba(245,158,11,0.1)]" 
                          : "border-zinc-900 bg-zinc-900/10 hover:border-zinc-800 hover:bg-zinc-900/20"
                      }`}
                    >
                      <div className="flex justify-between items-start mb-2">
                        <span className="font-bold text-xs text-amber-400">MOCK</span>
                        <Server className="w-4 h-4 text-amber-400" />
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-relaxed">
                        한투 모의투자 서버 연동. 가상 계좌에 모의 증권사 API Key 등록 필요.
                      </p>
                    </div>

                    <div 
                      onClick={() => setSettings({ ...settings, trade_mode: "REAL" })}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        settings.trade_mode === "REAL" 
                          ? "border-red-500 bg-red-500/5 shadow-[0_0_15px_rgba(239,68,68,0.1)]" 
                          : "border-zinc-900 bg-zinc-900/10 hover:border-zinc-800 hover:bg-zinc-900/20"
                      }`}
                    >
                      <div className="flex justify-between items-start mb-2">
                        <span className="font-bold text-xs text-red-500">REAL</span>
                        <ShieldAlert className="w-4 h-4 text-red-500" />
                      </div>
                      <p className="text-[10px] text-zinc-500 leading-relaxed">
                        실제 현금 기반 실전 자동매매. 고도로 검증된 상태에서만 신중하게 연동할 것.
                      </p>
                    </div>
                  </div>
                </div>

                {/* 섹션 2. 증권사 연동 설정 */}
                <div className="space-y-4 pt-6 border-t border-zinc-900">
                  <div className="flex flex-col gap-1.5 pb-2">
                    <h2 className="text-sm font-bold text-zinc-100 flex items-center gap-2">
                      <Key className="w-4 h-4 text-amber-400" />
                      2단계: 증권사 API 연동 정보 (Broker Config)
                    </h2>
                    <p className="text-[11px] text-zinc-400 leading-relaxed">
                      매매 주문을 직접 송신할 증권사 연동 정보 및 API Key를 연동합니다. KIS 모의/실전 거래 시 필수입니다.
                    </p>
                  </div>
                  
                  {settings.trade_mode === "SIMULATED" ? (
                    <div className="p-4 rounded-xl border border-blue-500/20 bg-blue-500/5 flex items-center gap-3">
                      <ShieldCheck className="w-5 h-5 text-blue-400 shrink-0" />
                      <div className="text-[11px] text-zinc-400 leading-relaxed">
                        현재 안전한 <strong>SIMULATED (가상 모의투자) 모드</strong>가 활성화되어 있습니다. 
                        가상 투자는 증권사 API Key 입력 없이 즉시 백엔드 엔진이 작동하므로 키를 입력하실 필요가 없습니다.
                      </div>
                    </div>
                  ) : (
                    <div className="space-y-4 animate-in fade-in slide-in-from-top-1 duration-300">
                      <div>
                        <label className="block text-xs font-semibold text-zinc-400 mb-1.5">Provider</label>
                        <select 
                          value={settings.broker_provider}
                          onChange={(e) => setSettings({ ...settings, broker_provider: e.target.value })}
                          className="w-full bg-zinc-950 border border-zinc-900 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none text-xs transition-all"
                        >
                          <option value="KIS">Korea Investment & Securities (KIS)</option>
                          <option value="TOSS" disabled>Toss Securities (Coming Soon)</option>
                        </select>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-zinc-400 mb-1.5">APP KEY</label>
                        <input 
                          type="text" 
                          value={settings.kis_app_key || ""}
                          onChange={(e) => setSettings({ ...settings, kis_app_key: e.target.value })}
                          placeholder="Enter your API Key"
                          className="w-full bg-zinc-950 border border-zinc-900 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-zinc-400 mb-1.5">APP SECRET</label>
                        <input 
                          type="password" 
                          value={settings.kis_app_secret || ""}
                          onChange={(e) => setSettings({ ...settings, kis_app_secret: e.target.value })}
                          placeholder="Enter your API Secret"
                          className="w-full bg-zinc-950 border border-zinc-900 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                        />
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-zinc-400 mb-1.5">ACCOUNT NO (계좌번호)</label>
                        <input 
                          type="text" 
                          value={settings.kis_account_no || ""}
                          onChange={(e) => setSettings({ ...settings, kis_account_no: e.target.value })}
                          placeholder="e.g. 12345678-01"
                          className="w-full bg-zinc-950 border border-zinc-900 rounded-xl p-3 text-white focus:ring-1 focus:ring-blue-500 focus:border-blue-500 outline-none font-mono text-xs transition-all"
                        />
                      </div>
                    </div>
                  )}
                </div>

                {/* 원스톱 저장 버튼 */}
                <div className="flex justify-end pt-6 border-t border-zinc-900">
                  <button 
                    onClick={() => handleSave(false)}
                    disabled={isSaving}
                    className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all active:scale-95 flex items-center gap-2 cursor-pointer shadow-md shadow-blue-900/30"
                  >
                    {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    설정 저장 및 연동 검증
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
                  <p className="text-xs text-zinc-400 leading-relaxed">
                    텔레그램 메신저 브릿지를 구축하여 모바일 환경에서 봇의 실시간 매수/매도 활동 및 계좌 잔고를 원격 제어합니다.
                  </p>
                </div>
                
                <div className="space-y-4">
                  <div className="flex justify-between items-center bg-zinc-900/30 border border-zinc-900 rounded-xl p-4">
                    <span className="text-xs font-semibold text-zinc-300">텔레그램 비동기 알림 연동</span>
                    <label className="relative inline-flex items-center cursor-pointer select-none">
                      <input 
                        type="checkbox" 
                        checked={settings.telegram_enabled} 
                        onChange={(e) => setSettings({ ...settings, telegram_enabled: e.target.checked })}
                        className="sr-only peer"
                      />
                      <div className="w-9 h-5 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-zinc-500 after:border-zinc-500 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-indigo-500"></div>
                    </label>
                  </div>

                  <div className="space-y-6">
                    <div className="p-4 rounded-xl border border-indigo-500/20 bg-indigo-500/5 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-indigo-400">⚡ 1-Click 간편 자동 연동 (추천)</span>
                      </div>
                      <p className="text-[10px] text-zinc-400 leading-relaxed">
                        아래 버튼을 클릭하여 공식 텔레그램 봇으로 이동한 뒤, 대화창 하단의 <strong>[시작 (Start)]</strong> 버튼을 한 번만 클릭하시면 계정이 자동으로 즉시 연동됩니다.
                      </p>
                      
                      <a
                        href={settings.telegram_enabled && settings.global_bot_username ? `https://t.me/${settings.global_bot_username}?start=${username}` : "#"}
                        onClick={(e) => {
                          if (!settings.telegram_enabled) {
                            e.preventDefault();
                            toast.warning("상단의 '텔레그램 연동' 스위치를 먼저 켜주세요!");
                          }
                        }}
                        target="_blank"
                        rel="noopener noreferrer"
                        className={`inline-flex w-full items-center justify-center gap-2 px-4 py-3 rounded-xl text-xs font-black transition-all active:scale-[0.98] shadow-md ${
                          settings.telegram_enabled 
                            ? "bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 text-white shadow-indigo-500/20" 
                            : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                        }`}
                      >
                        <Send className="w-3.5 h-3.5" />
                        공식 텔레그램 연동 시작하기
                      </a>
                    </div>

                    <div className="p-4 rounded-xl border border-zinc-900 bg-zinc-900/10 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-zinc-400">⚙️ 수동 CHAT ID 연동</span>
                      </div>
                      <div className="pt-1">
                        <input 
                          type="text" 
                          value={settings.telegram_chat_id || ""}
                          onChange={(e) => setSettings({ ...settings, telegram_chat_id: e.target.value })}
                          placeholder="예: 987654321"
                          disabled={!settings.telegram_enabled}
                          className="w-full bg-zinc-950 border border-zinc-900 rounded-xl p-3 text-white focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 outline-none font-mono text-xs disabled:opacity-40 transition-all"
                        />
                      </div>
                    </div>
                  </div>
                </div>

                <div className="flex justify-end pt-6 border-t border-zinc-900">
                  <button 
                    onClick={() => handleSave(false)}
                    disabled={isSaving}
                    className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer"
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
                  <p className="text-xs text-red-400/70 leading-relaxed pr-4">
                    모의 계좌 강제 포맷 및 주식 일괄 즉시 청산과 같은 극도의 위험성을 동반한 시스템 제어 기능을 모아 두었습니다.
                  </p>
                </div>
                
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="p-4 bg-zinc-900/20 rounded-xl border border-zinc-900 flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                        <RefreshCw className="w-3.5 h-3.5 text-zinc-400" />
                        모의투자 자산 초기화
                      </h3>
                      <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                        모의투자(SIMULATED) 모드의 주식 잔고와 모든 매매 내역을 완전히 포맷합니다.
                      </p>
                    </div>
                    <div className="mt-4">
                      {settings.trade_mode === "SIMULATED" ? (
                        <button
                          onClick={() => setShowResetModal(true)}
                          className="w-full py-2 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 text-xs font-bold transition-all active:scale-[0.98] cursor-pointer"
                        >
                          가상 잔고 초기화
                        </button>
                      ) : (
                        <p className="text-[10px] text-zinc-500 text-center font-semibold italic bg-zinc-950/50 py-2 rounded-lg">
                          ※ 모의투자(SIMULATED) 전용
                        </p>
                      )}
                    </div>
                  </div>

                  <div className="p-4 bg-zinc-900/20 rounded-xl border border-zinc-900 flex flex-col justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                        <Ban className="w-3.5 h-3.5 text-zinc-400" />
                        보유 주식 일괄 강제 청산
                      </h3>
                      <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                        현재 보유 중인 모든 주식을 실시간 시장 가격으로 즉시 일괄 매도 처분합니다.
                      </p>
                    </div>
                    <div className="mt-4">
                      <button
                        onClick={() => setShowLiquidateModal(true)}
                        className="w-full py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all active:scale-[0.98] flex items-center justify-center gap-1 cursor-pointer"
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

        {/* Modal 1: Real Trading Warning */}
        {showRealWarning && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowRealWarning(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                  <ShieldAlert className="w-7 h-7 text-red-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">⚠️ 실전 트레이딩 모드 전환 확인</h3>
                <div className="space-y-2">
                  <p className="text-xs text-red-400 font-bold leading-relaxed">
                    경고: 실제 현금이 투입되는 실전 모드로 전환됩니다.
                  </p>
                  <p className="text-[11px] text-zinc-400 leading-relaxed">
                    실전 모드에서는 자동매매 엔진이 <strong className="text-red-400">실제 증권 계좌의 현금</strong>으로 주식을 매수/매도합니다.
                    발생한 손실은 <strong className="text-red-400">절대 되돌릴 수 없으며</strong>, 시스템 오류 또는 알고리즘 판단 실패로 인한 금전적 피해에 대해 전적으로 본인이 책임져야 합니다.
                  </p>
                  <p className="text-[11px] text-amber-400/80 font-semibold leading-relaxed">
                    충분한 백테스팅과 모의투자 검증을 완료한 후에만 진행하십시오.
                  </p>
                </div>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowRealWarning(false)}
                    className="flex-1 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    취소
                  </button>
                  <button
                    onClick={() => handleSave(true)}
                    className="flex-1 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    <ShieldAlert className="w-3.5 h-3.5" />
                    실전 모드 저장
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Modal 2: Reset Balance Confirmation */}
        {showResetModal && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowResetModal(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-amber-500/10 flex items-center justify-center">
                  <RefreshCw className="w-7 h-7 text-amber-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">가상 계좌 자산 초기화</h3>
                <div className="space-y-2">
                  <p className="text-xs text-red-400 font-bold leading-relaxed">
                    ⚠️ 이 작업은 되돌릴 수 없습니다.
                  </p>
                  <p className="text-[11px] text-zinc-400 leading-relaxed">
                    모의투자 계좌의 <strong className="text-red-400">모든 보유 주식</strong>, <strong className="text-red-400">거래 기록</strong>, <strong className="text-red-400">활동 로그</strong>가 영구적으로 삭제되며
                    초기 상태로 완전히 포맷됩니다.
                  </p>
                </div>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowResetModal(false)}
                    className="flex-1 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    취소
                  </button>
                  <button
                    onClick={handleResetBalance}
                    disabled={isDangerActionLoading}
                    className="flex-1 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    {isDangerActionLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
                    초기화 실행
                  </button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Modal 3: Force Liquidate Confirmation */}
        {showLiquidateModal && (
          <div
            className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center"
            onClick={() => setShowLiquidateModal(false)}
          >
            <div
              className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl animate-in fade-in zoom-in-95 duration-200"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex flex-col items-center text-center gap-4">
                <div className="w-14 h-14 rounded-full bg-red-500/10 flex items-center justify-center">
                  <Trash2 className="w-7 h-7 text-red-500" />
                </div>
                <h3 className="text-lg font-extrabold text-white">보유 주식 전량 강제 청산</h3>
                <div className="space-y-2">
                  <p className="text-xs text-red-400 font-bold leading-relaxed">
                    ⚠️ 이 작업은 되돌릴 수 없습니다.
                  </p>
                  <p className="text-[11px] text-zinc-400 leading-relaxed">
                    현재 보유 중인 <strong className="text-red-400">모든 종목</strong>이 <strong className="text-red-400">시장가로 즉시 매도</strong>됩니다.
                    시장 상황에 따라 예상보다 불리한 가격에 체결될 수 있으며, 일단 실행되면 절대 되돌릴 수 없습니다.
                  </p>
                </div>
                <div className="flex gap-3 w-full pt-2">
                  <button
                    onClick={() => setShowLiquidateModal(false)}
                    className="flex-1 py-2.5 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-300 text-xs font-bold transition-all cursor-pointer"
                  >
                    취소
                  </button>
                  <button
                    onClick={handleForceLiquidate}
                    disabled={isDangerActionLoading}
                    className="flex-1 py-2.5 rounded-xl bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-bold transition-all cursor-pointer flex items-center justify-center gap-1.5"
                  >
                    {isDangerActionLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                    전량 청산 실행
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
