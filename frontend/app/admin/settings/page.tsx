"use client";

import React, { useState, useEffect, startTransition } from "react";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { 
  AlertTriangle, Server, ShieldCheck, ShieldAlert, Key, Save, Loader2, Send, 
  Users, UserMinus, ToggleLeft, ToggleRight, RefreshCw, Trash2, Ban,
  Globe, Plus, Search, Edit2, Check, X, HelpCircle
} from "lucide-react";
import api, { translationAPI } from "@/lib/api";

interface UserSettings {
  trade_mode: string;
  broker_provider: string;
  kis_app_key: string;
  kis_app_secret: string;
  kis_account_no: string;
  
  // Telegram Bot Settings
  telegram_chat_id: string;
  telegram_enabled: boolean;
  global_bot_username?: string;
}

interface ManagedUser {
  id: number;
  username: string;
  created_at: string;
  trade_mode: string;
  telegram_enabled: boolean;
  is_running: boolean;
}

interface TranslationItem {
  id: number;
  ticker: string;
  name_ko: string;
}

export default function AdminSettingsPage() {
  const router = useRouter();
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [activeTab, setActiveTab] = useState<"settings" | "users" | "translation">("settings");
  
  // --- 다국어 번역 사전(Translation) 상태 관리 ---
  const [translations, setTranslations] = useState<TranslationItem[]>([]);
  const [loadingTranslations, setLoadingTranslations] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 10;
  const [newTicker, setNewTicker] = useState<string>("");
  const [newNameKo, setNewNameKo] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState<string>("");

  // 개인 투자 설정 관련 State
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
  const [subTab, setSubTab] = useState<"mode" | "broker" | "telegram" | "danger">("mode");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [showRealWarning, setShowRealWarning] = useState(false);

  // 슈퍼어드민 관련 State
  const [usersList, setUsersList] = useState<ManagedUser[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(false);
  const [actionUserId, setActionUserId] = useState<number | null>(null);

  // 위험 영역 모달 관련 State
  const [showResetModal, setShowResetModal] = useState(false);
  const [showLiquidateModal, setShowLiquidateModal] = useState(false);
  const [isDangerActionLoading, setIsDangerActionLoading] = useState(false);

  // Auth Guard & Admin 권한 조회
  useEffect(() => {
    const token = localStorage.getItem("stockauto_token");
    const storedUsername = localStorage.getItem("stockauto_username");

    if (!token) {
      router.push("/login");
    } else {
      startTransition(() => {
        setIsAuthenticated(true);
        setUsername(storedUsername || "");
        if (storedUsername === "admin") {
          setIsAdmin(true);
        }
      });
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
  };

  const fetchUsers = async () => {
    if (!isAdmin) return;
    setIsLoadingUsers(true);
    try {
      const res = await api.get("/admin/users");
      setUsersList(res.data);
    } catch (err) {
      const error = err as Error;
      toast.error(error.message || "사용자 목록을 불러오는 데 실패했습니다.");
    } finally {
      setIsLoadingUsers(false);
    }
  };

  const fetchTranslations = async () => {
    setLoadingTranslations(true);
    try {
      const res = await translationAPI.getAll();
      setTranslations(res.data);
    } catch (err) {
      const error = err as Error;
      toast.error(`사전 데이터 로드 실패: ${error.message}`);
    } finally {
      setLoadingTranslations(false);
    }
  };

  useEffect(() => {
    if (!isAuthenticated) return;

    void (async () => {
      await fetchSettings();
      if (isAdmin) {
        if (activeTab === "users") {
          await fetchUsers();
        } else if (activeTab === "translation") {
          await fetchTranslations();
        }
      }
    })();
  }, [isAuthenticated, isAdmin, activeTab]);

  const handleSave = async (forceReal = false) => {
    // 1. 유효성 검사 (조기 반환으로 서버 저장 원천 차단)
    if (settings.trade_mode === "MOCK" || settings.trade_mode === "REAL") {
      const key = settings.kis_app_key;
      const placeholderKeys: (string | null | undefined)[] = ["YOUR_APP_KEY_HERE", "your_virtual_app_key_here", "your_real_app_key_here", "your_app_key_here", "", null, undefined];
      if (placeholderKeys.includes(key)) {
        toast.error(`[저장 실패] ${settings.trade_mode} 모드를 사용하려면 'Broker Config' 탭에서 유효한 증권사 API 키를 먼저 입력해야 합니다.`);
        return;
      }
    }

    // 2. REAL 모드 2차 안전 경고 모달 처리
    if (settings.trade_mode === "REAL" && !forceReal) {
      setShowRealWarning(true);
      return;
    }
    
    setShowRealWarning(false);
    setIsSaving(true);
    
    try {
      // KIS API Key 실시간 통신 검증 트리거 (Phase 13)
      let verifySuccess = true;
      let verifyMessage = "";
      
      if (settings.trade_mode === "MOCK" || settings.trade_mode === "REAL") {
        try {
          const verifyRes = await api.post("/admin/verify-kis", settings);
          verifySuccess = verifyRes.data.success;
          verifyMessage = verifyRes.data.message;
        } catch (verifyErr) {
          const err = verifyErr as Error;
          verifySuccess = false;
          verifyMessage = err.message || "통신 검증 중 오류가 발생했습니다.";
        }
      }
      
      // 설정값은 검증 실패 여부와 무관하게 DB에 저장
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
          {
            duration: 8000,
          }
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
      const error = err as Error;
      toast.error(error.message || "설정 저장에 실패했습니다.");
    } finally {
      setIsSaving(false);
    }
  };

  // 1. 모의 투자금 & 로그 초기화 액션
  const handleResetBalance = async () => {
    setIsDangerActionLoading(true);
    try {
      await api.post("/account/reset-balance");
      toast.success("가상 계좌 자산 및 모든 로그가 성공적으로 리셋되었습니다!");
      setShowResetModal(false);
      await fetchSettings();
    } catch (err) {
      const error = err as Error;
      toast.error(error.message || "계좌 초기화에 실패했습니다.");
    } finally {
      setIsDangerActionLoading(false);
    }
  };

  // 2. 보유 주식 전량 일괄 강제 청산 액션
  const handleForceLiquidate = async () => {
    setIsDangerActionLoading(true);
    try {
      const res = await api.post("/account/force-liquidate");
      toast.success(res.data.message || "보유 중인 주식이 모두 전량 청산되었습니다.");
      setShowLiquidateModal(false);
    } catch (err) {
      const error = err as Error;
      toast.error(error.message || "일괄 청산 도중 오류가 발생했습니다.");
    } finally {
      setIsDangerActionLoading(false);
    }
  };

  // [슈퍼어드민] 유저 봇 원격 기동/일시정지
  const handleToggleUserBot = async (userId: number) => {
    setActionUserId(userId);
    try {
      const res = await api.post(`/admin/users/${userId}/toggle-bot`);
      toast.success(res.data.is_running ? "봇이 성공적으로 가동되었습니다." : "봇이 일시정지 되었습니다.");
      await fetchUsers();
    } catch (err) {
      const error = err as Error;
      toast.error(error.message || "봇 상태 변경에 실패했습니다.");
    } finally {
      setActionUserId(null);
    }
  };

  // [슈퍼어드민] 유저 계정 영구 삭제
  const handleDeleteUser = async (userId: number, username: string) => {
    if (!confirm(`🚨 경고: 정말로 [${username}] 사용자를 영구 삭제하시겠습니까?\n이 작업은 되돌릴 수 없으며, 모든 잔고 및 거래 내역이 삭제됩니다.`)) {
      return;
    }
    setActionUserId(userId);
    try {
      await api.post(`/admin/users/${userId}/delete`);
      toast.success(`[${username}] 계정이 안전하게 영구 삭제되었습니다.`);
      await fetchUsers();
    } catch (err) {
      const error = err as Error;
      toast.error(error.message || "사용자 삭제에 실패했습니다.");
    } finally {
      setActionUserId(null);
    }
  };

  // 새로운 번역 신규 저장
  const handleCreateTranslation = async (e: React.FormEvent) => {
    e.preventDefault();
    const tickerClean = newTicker.trim().toUpperCase();
    const nameClean = newNameKo.trim();

    if (!tickerClean || !nameClean) {
      toast.warning("티커와 한국어 이름을 모두 입력해 주세요.");
      return;
    }

    setIsSubmitting(true);
    try {
      await translationAPI.save(tickerClean, nameClean);
      toast.success(`${tickerClean} (${nameClean}) 등록 완료! (메모리 캐시 자동 핫싱크)`);
      setNewTicker("");
      setNewNameKo("");
      await fetchTranslations();
    } catch (err) {
      const error = err as Error;
      toast.error(`번역 등록 실패: ${error.message}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 인라인 에디팅 시작
  const startEditTranslation = (item: TranslationItem) => {
    setEditingId(item.id);
    setEditingName(item.name_ko);
  };

  // 인라인 에디팅 저장
  const handleUpdateTranslation = async (id: number) => {
    const nameClean = editingName.trim();
    if (!nameClean) {
      toast.warning("한국어 이름을 입력해 주세요.");
      return;
    }

    try {
      await translationAPI.update(id, nameClean);
      toast.success("번역이 수정되었으며 백엔드 캐시가 즉시 동기화되었습니다!");
      setEditingId(null);
      await fetchTranslations();
    } catch (err) {
      const error = err as Error;
      toast.error(`수정 실패: ${error.message}`);
    }
  };

  // 번역 데이터 삭제
  const handleDeleteTranslation = async (id: number, ticker: string) => {
    if (!confirm(`${ticker} 번역 매핑을 정말 삭제하시겠습니까?\n삭제 즉시 메모리 캐시에서도 분리됩니다.`)) {
      return;
    }

    try {
      await translationAPI.delete(id);
      toast.success(`${ticker} 번역 매핑이 성공적으로 제거되었습니다.`);
      await fetchTranslations();
    } catch (err) {
      const error = err as Error;
      toast.error(`삭제 실패: ${error.message}`);
    }
  };

  // 실시간 타이핑 필터 필터링 결과 계산
  const filteredTranslations = translations.filter(
    (t) =>
      t.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.name_ko.toLowerCase().includes(searchQuery.toLowerCase())
  );

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
        
        {/* 상단 탭 헤더 */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between border-b border-zinc-800 pb-4 mb-8 gap-4">
          <div>
            <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400 mb-1">
              {isAdmin ? "어드민 설정 & 사용자 관리" : "개인 투자 설정"}
            </h1>
            <p className="text-zinc-400 text-xs">
              {isAdmin 
                ? "트레이딩 엔진의 글로벌 설정과 플랫폼에 등록된 모든 사용자들의 상태를 총괄 제어합니다." 
                : "개인 트레이딩 엔진 설정 및 증권사 API Key, 텔레그램 연동 정보를 관리합니다."}
            </p>
          </div>

          {/* 슈퍼어드민인 경우 탭 인터페이스 표시 */}
          {isAdmin && (
            <div className="flex space-x-1.5 bg-zinc-900/60 p-1 rounded-xl border border-zinc-800/80 self-start">
              <button
                onClick={() => setActiveTab("settings")}
                className={`px-4 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-200 cursor-pointer ${
                  activeTab === "settings"
                    ? "bg-zinc-800 text-white shadow-inner"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                ⚙️ 나의 설정
              </button>
              <button
                onClick={() => setActiveTab("users")}
                className={`px-4 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-200 cursor-pointer ${
                  activeTab === "users"
                    ? "bg-zinc-800 text-white shadow-inner"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                👥 전체 사용자 관리 (Admin)
              </button>
              <button
                onClick={() => setActiveTab("translation")}
                className={`px-4 py-2 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-200 cursor-pointer ${
                  activeTab === "translation"
                    ? "bg-zinc-800 text-white shadow-inner"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                🌐 다국어 번역 관리 (Admin)
              </button>
            </div>
          )}
        </div>

        {activeTab === "settings" && (
          /* ========================================================================= */
          /* ⚙️ 나의 투자 설정 뷰 (Vercel / Linear Style Sidebar Navigation Layout)    */
          /* ========================================================================= */
          <div className="flex flex-col md:flex-row gap-8 items-start">
            
            {/* 좌측 사이드바 내비게이션 */}
            <div className="w-full md:w-48 shrink-0 flex flex-row md:flex-col gap-1 bg-zinc-950 md:bg-transparent pb-3 md:pb-0 border-b md:border-b-0 border-zinc-900 overflow-x-auto md:overflow-x-visible">
              {[
                { id: "mode", label: "Trading Mode", icon: Server, color: "text-blue-400" },
                { id: "broker", label: "Broker Config", icon: Key, color: "text-amber-400" },
                { id: "telegram", label: "Telegram Bridge", icon: Send, color: "text-indigo-400" },
                { id: "danger", label: "Danger Zone", icon: AlertTriangle, color: "text-red-500" },
              ].map((item) => {
                const Icon = item.icon;
                const isActive = subTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setSubTab(item.id as "mode" | "broker" | "telegram" | "danger")}
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

            {/* 우측 상세 설정 내용 */}
            <div className="flex-1 min-w-0 w-full">
              
              {/* 1. Trading Mode Section */}
              {subTab === "mode" && (
                <div className="space-y-6">
                  <div className="flex flex-col gap-1.5 pb-4 border-b border-zinc-900">
                    <h2 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                      <Server className="w-4 h-4 text-blue-400" />
                      Trading Mode
                    </h2>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      트레이딩 엔진의 실행 모드를 선택합니다. 가상 데이터 시뮬레이션부터 KIS 증권사의 모의서버 및 실거래 구동 환경을 제어합니다.
                    </p>
                  </div>
                  
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    {/* SIMULATED */}
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

                    {/* MOCK */}
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

                    {/* REAL */}
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

                  {/* Action Buttons */}
                  <div className="flex justify-end pt-6 border-t border-zinc-900">
                    <button 
                      onClick={() => handleSave(false)}
                      disabled={isSaving}
                      className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all active:scale-95 flex items-center gap-2 cursor-pointer shadow-md shadow-blue-900/30"
                    >
                      {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      저장
                    </button>
                  </div>
                </div>
              )}

              {/* 2. Broker Configuration Section */}
              {subTab === "broker" && (
                <div className="space-y-6">
                  <div className="flex flex-col gap-1.5 pb-4 border-b border-zinc-900">
                    <h2 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                      <Key className="w-4 h-4 text-amber-400" />
                      Broker Config
                    </h2>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      매매를 실행할 증권사를 지정하고 API 인증 키 정보를 연동합니다. 입력값은 사용자 안전을 위해 양방향 암호화 처리됩니다.
                    </p>
                  </div>
                  
                  <div className="space-y-4">
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

                  {/* Action Buttons */}
                  <div className="flex justify-end pt-6 border-t border-zinc-900">
                    <button 
                      onClick={() => handleSave(false)}
                      disabled={isSaving}
                      className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all active:scale-95 flex items-center gap-2 cursor-pointer shadow-md shadow-blue-900/30"
                    >
                      {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      저장
                    </button>
                  </div>
                </div>
              )}

              {/* 3. Telegram Configuration Section */}
              {subTab === "telegram" && (
                <div className="space-y-6">
                  <div className="flex flex-col gap-1.5 pb-4 border-b border-zinc-900">
                    <h2 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                      <Send className="w-4 h-4 text-indigo-400" />
                      Telegram Bridge
                    </h2>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      텔레그램 메신저 브릿지를 구축하여 모바일 환경에서 봇의 실시간 매수/매도 활동 및 계좌 잔고를 원격 제어하고 알림을 받아봅니다.
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
                      {/* 1. 간편 자동 연동 (Deep Link) */}
                      <div className="p-4 rounded-xl border border-indigo-500/20 bg-indigo-500/5 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-indigo-400">⚡ 1-Click 간편 자동 연동 (추천)</span>
                          <span className="text-[9px] bg-indigo-500/20 text-indigo-400 px-2 py-0.5 rounded font-semibold uppercase">Easy Link</span>
                        </div>
                        <p className="text-[10px] text-zinc-400 leading-relaxed">
                          복잡하게 챗 ID를 찾아서 적을 필요가 없습니다! 아래 버튼을 클릭하여 공식 텔레그램 봇으로 이동한 뒤, 
                          대화창 하단의 <strong>[시작 (Start)]</strong> 버튼을 한 번만 클릭하시면 계정이 자동으로 즉시 연동됩니다.
                        </p>
                        
                        <a
                          href={settings.telegram_enabled && settings.global_bot_username ? `https://t.me/${settings.global_bot_username}?start=${username}` : "#"}
                          onClick={(e) => {
                            if (!settings.telegram_enabled) {
                              e.preventDefault();
                              toast.warning("상단의 '텔레그램 비동기 알림 연동' 스위치를 먼저 켜주세요!");
                            }
                          }}
                          target="_blank"
                          rel="noopener noreferrer"
                          className={`inline-flex w-full items-center justify-center gap-2 px-4 py-3 rounded-xl text-xs font-black transition-all active:scale-[0.98] shadow-md ${
                            settings.telegram_enabled 
                              ? "bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 hover:from-indigo-600 hover:to-pink-600 text-white cursor-pointer shadow-indigo-500/20" 
                              : "bg-zinc-800 text-zinc-500 cursor-not-allowed"
                          }`}
                        >
                          <Send className="w-3.5 h-3.5" />
                          공식 텔레그램 연동 시작하기
                        </a>
                      </div>

                      {/* 2. 수동 연동 (예비용) */}
                      <div className="p-4 rounded-xl border border-zinc-900 bg-zinc-900/10 space-y-3">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-zinc-400">⚙️ 수동 CHAT ID 연동 (예비용)</span>
                          <span className="text-[9px] text-zinc-500 font-mono">TELEGRAM_CHAT_ID</span>
                        </div>
                        <p className="text-[10px] text-zinc-500 leading-relaxed">
                          본인의 텔레그램 CHAT ID를 이미 알고 계시다면 아래에 직접 입력하여 연동할 수도 있습니다.
                          (챗 ID는 텔레그램에서 <code>@userinfobot</code> 또는 <code>@myidbot</code> 등을 통해 조회하실 수 있습니다.)
                        </p>
                        
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

                      <div className="text-[10px] text-zinc-500 bg-zinc-900/20 p-3 rounded-lg border border-zinc-900/50 leading-relaxed">
                        ℹ️ 텔레그램 연동 완료 후 봇 대화방에서 <code>/status</code>(계좌 잔고 조회), <code>/stop</code>(자동 매매 일시정지), <code>/run</code>(자동 매매 가동) 명령어를 입력하여 원격으로 시스템을 제어하실 수 있습니다.
                      </div>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="flex justify-end pt-6 border-t border-zinc-900">
                    <button 
                      onClick={() => handleSave(false)}
                      disabled={isSaving}
                      className="bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white px-5 py-2.5 rounded-xl text-xs font-bold transition-all active:scale-95 flex items-center gap-2 cursor-pointer shadow-md shadow-blue-900/30"
                    >
                      {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      저장
                    </button>
                  </div>
                </div>
              )}

              {/* 5. Danger Zone Section */}
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
                    {/* 1. 모의투자 잔고 초기화 */}
                    <div className="p-4 bg-zinc-900/20 rounded-xl border border-zinc-900 flex flex-col justify-between">
                      <div>
                        <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                          <RefreshCw className="w-3.5 h-3.5 text-zinc-400" />
                          모의투자 자산 초기화
                        </h3>
                        <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                          모의투자(SIMULATED) 모드의 주식 잔고와 모든 매매/활동 내역을 완전히 포맷하고, 최초 가상 예수금(1,000만 원) 상태로 복원합니다.
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
                            ※ 모의투자(SIMULATED) 모드 전용
                          </p>
                        )}
                      </div>
                    </div>

                    {/* 2. 보유 주식 전량 강제 청산 */}
                    <div className="p-4 bg-zinc-900/20 rounded-xl border border-zinc-900 flex flex-col justify-between">
                      <div>
                        <h3 className="text-xs font-bold text-zinc-300 flex items-center gap-1.5">
                          <Ban className="w-3.5 h-3.5 text-zinc-400" />
                          보유 주식 일괄 강제 청산
                        </h3>
                        <p className="text-[10px] text-zinc-500 mt-1.5 leading-relaxed">
                          현재 보유 중인 모든 주식을 실시간 시장 가격으로 즉시 일괄 강제 매도 처분합니다. 급락장 비상 대응 및 포트폴리오 비우기에 활용됩니다.
                        </p>
                      </div>
                      <div className="mt-4">
                        <button
                          onClick={() => setShowLiquidateModal(true)}
                          className="w-full py-2 rounded-xl bg-red-600 hover:bg-red-700 text-white text-xs font-bold transition-all active:scale-[0.98] cursor-pointer flex items-center justify-center gap-1"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          보유 주식 전량 청산
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              )}

            </div>
          </div>
        )}

        {activeTab === "users" && (
          /* ========================================================================= */
          /* 👥 전체 사용자 관리 뷰 (Super Admin 전용)                                  */
          /* ========================================================================= */
          <div className="backdrop-blur-xl bg-zinc-900/30 rounded-2xl border border-zinc-800 p-6 shadow-lg">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <Users className="w-5 h-5 text-emerald-400" />
                전체 가입자 현황 모니터링
              </h2>
              <button
                onClick={fetchUsers}
                disabled={isLoadingUsers}
                className="p-1.5 bg-zinc-800/80 hover:bg-zinc-700 rounded-lg transition-colors border border-zinc-700/50"
                title="새로고침"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isLoadingUsers ? "animate-spin text-blue-400" : "text-zinc-300"}`} />
              </button>
            </div>

            {isLoadingUsers ? (
              <div className="py-20 flex justify-center">
                <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
              </div>
            ) : usersList.length === 0 ? (
              <div className="py-20 text-center text-zinc-500 text-sm">
                가입된 사용자가 없습니다.
              </div>
            ) : (
              <div className="overflow-x-auto rounded-xl border border-zinc-800/80 bg-zinc-950/40">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="bg-zinc-900/80 border-b border-zinc-800 text-zinc-400 font-bold uppercase tracking-wider">
                      <th className="p-4">ID</th>
                      <th className="p-4">사용자명</th>
                      <th className="p-4">가입일시</th>
                      <th className="p-4">구동 모드</th>
                      <th className="p-4">텔레그램</th>
                      <th className="p-4 text-center">봇 상태</th>
                      <th className="p-4 text-right">제어</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersList.map((u) => (
                      <tr key={u.id} className="border-b border-zinc-800/60 hover:bg-zinc-900/30 transition-colors">
                        <td className="p-4 font-mono font-bold text-zinc-500">{u.id}</td>
                        <td className="p-4">
                          <span className="font-semibold text-white bg-zinc-900 px-2.5 py-1 rounded-lg border border-zinc-800">
                            {u.username}
                          </span>
                        </td>
                        <td className="p-4 text-zinc-400 font-mono">
                          {new Date(u.created_at).toLocaleDateString()} {new Date(u.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </td>
                        <td className="p-4">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase tracking-wider ${
                            u.trade_mode === 'REAL' 
                              ? 'bg-red-500/20 text-red-400 border border-red-500/30' 
                              : u.trade_mode === 'MOCK'
                              ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                              : 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                          }`}>
                            {u.trade_mode}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className={`text-[10px] font-semibold ${u.telegram_enabled ? "text-indigo-400" : "text-zinc-500"}`}>
                            {u.telegram_enabled ? "🟢 연동 중" : "⚪ 비활성"}
                          </span>
                        </td>
                        <td className="p-4 text-center">
                          <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${
                            u.is_running ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-zinc-800 text-zinc-500"
                          }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${u.is_running ? "bg-emerald-500 animate-pulse" : "bg-zinc-500"}`}></span>
                            {u.is_running ? "가동 중" : "정지"}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <div className="flex items-center justify-end space-x-2.5">
                            {/* 봇 원격 제어 토글 */}
                            <button
                              onClick={() => handleToggleUserBot(u.id)}
                              disabled={actionUserId === u.id}
                              className={`p-1.5 rounded-lg border transition-all cursor-pointer ${
                                u.is_running
                                  ? "bg-red-500/10 hover:bg-red-500/20 border-red-500/20 text-red-400"
                                  : "bg-emerald-500/10 hover:bg-emerald-500/20 border-emerald-500/20 text-emerald-400"
                              }`}
                              title={u.is_running ? "봇 일시정지" : "봇 가동시키기"}
                            >
                              {actionUserId === u.id ? (
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              ) : u.is_running ? (
                                <ToggleRight className="w-4 h-4" />
                              ) : (
                                <ToggleLeft className="w-4 h-4" />
                              )}
                            </button>

                            {/* 유저 계정 강제 삭제 */}
                            {u.username !== "admin" && (
                              <button
                                onClick={() => handleDeleteUser(u.id, u.username)}
                                disabled={actionUserId === u.id}
                                className="p-1.5 bg-zinc-950 hover:bg-red-500/10 border border-zinc-800 hover:border-red-500/20 text-zinc-500 hover:text-red-400 rounded-lg transition-all cursor-pointer"
                                title="계정 강제 영구 삭제"
                              >
                                {actionUserId === u.id ? (
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                ) : (
                                  <UserMinus className="w-4 h-4" />
                                )}
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {activeTab === "translation" && (
          /* ========================================================================= */
          /* 🌐 다국어 번역 관리 뷰 (Super Admin 전용)                                   */
          /* ========================================================================= */
          <div className="space-y-6 animate-in fade-in duration-200">
            
            {/* A. 새로운 번역 등록 인라인 폼 */}
            <div className="bg-zinc-900/30 backdrop-blur-xl rounded-2xl border border-zinc-800 p-6 shadow-lg space-y-4">
              <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                <h2 className="text-base font-semibold flex items-center gap-2">
                  <Plus className="w-4 h-4 text-blue-400" />
                  신규 주식 한글명 커스텀 등록
                </h2>
                <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded">
                  AUTO SYNC ACTIVE
                </span>
              </div>
              
              <form onSubmit={handleCreateTranslation} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                <div className="text-xs">
                  <label className="block text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">
                    미국 주식 Ticker (영어)
                  </label>
                  <input
                    type="text"
                    placeholder="예: TSLA"
                    value={newTicker}
                    onChange={(e) => setNewTicker(e.target.value)}
                    className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 tracking-widest font-mono uppercase"
                    disabled={isSubmitting}
                  />
                </div>
                <div className="text-xs">
                  <label className="block text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">
                    한국어 치환 이름 (한글)
                  </label>
                  <input
                    type="text"
                    placeholder="예: 테슬라"
                    value={newNameKo}
                    onChange={(e) => setNewNameKo(e.target.value)}
                    className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    disabled={isSubmitting}
                  />
                </div>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-xs py-2.5 px-4 rounded-xl shadow-lg shadow-indigo-950/20 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center gap-2 cursor-pointer"
                >
                  {isSubmitting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      등록 중...
                    </>
                  ) : (
                    "번역 사전에 즉시 등록"
                  )}
                </button>
              </form>
            </div>

            {/* B. 데이터 테이블 필터 및 조회 영역 */}
            <div className="bg-zinc-900/30 backdrop-blur-xl rounded-2xl border border-zinc-800 p-6 shadow-lg space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-800 pb-4">
                <div>
                  <h2 className="text-base font-semibold flex items-center gap-2">
                    <Globe className="w-4 h-4 text-emerald-400" />
                    주식 한글화 기준정보 데이터 목록
                  </h2>
                  <p className="text-xs text-zinc-400 mt-1">
                    전체 사전에 저장된 번역 데이터 수: <strong className="text-emerald-400">{translations.length}개</strong>
                  </p>
                </div>
                
                {/* 실시간 필터 인풋 필드 */}
                <div className="relative max-w-xs w-full">
                  <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
                  <input
                    type="text"
                    placeholder="티커 또는 한글명 검색..."
                    value={searchQuery}
                    onChange={(e) => {
                      setSearchQuery(e.target.value);
                      setCurrentPage(1);
                    }}
                    className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                  />
                </div>
              </div>

              {/* C. 데이터 그리드 테이블 */}
              <div className="overflow-x-auto rounded-xl border border-zinc-800/80 bg-zinc-950/40">
                {loadingTranslations ? (
                  <div className="py-20 flex flex-col items-center justify-center gap-3">
                    <Loader2 className="w-8 h-8 animate-spin text-zinc-500" />
                    <span className="text-xs text-zinc-500 font-semibold">데이터베이스 로딩 중...</span>
                  </div>
                ) : filteredTranslations.length === 0 ? (
                  <div className="py-16 text-center">
                    <Globe className="mx-auto w-12 h-12 text-zinc-700 mb-3" />
                    <p className="text-xs font-semibold text-zinc-500">등록되었거나 검색 조건에 부합하는 데이터가 없습니다.</p>
                    <p className="text-[11px] text-zinc-600 mt-1">상단 폼을 이용하여 첫 번역 주식을 등록해 보세요!</p>
                  </div>
                ) : (() => {
                  // 페이징 계산식 실행
                  const totalPages = Math.ceil(filteredTranslations.length / itemsPerPage);
                  const indexOfLastItem = currentPage * itemsPerPage;
                  const indexOfFirstItem = indexOfLastItem - itemsPerPage;
                  const currentItems = filteredTranslations.slice(indexOfFirstItem, indexOfLastItem);
                  
                  return (
                    <>
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-zinc-900/80 border-b border-zinc-800 text-zinc-400 font-bold uppercase tracking-wider">
                            <th className="p-4">ID</th>
                            <th className="p-4">Ticker (티커)</th>
                            <th className="p-4">Korean Name (한글 이름)</th>
                            <th className="p-4 text-right">Actions (작업)</th>
                          </tr>
                        </thead>
                        <tbody>
                          {currentItems.map((item) => (
                            <tr 
                              key={item.id} 
                              className={`border-b border-zinc-800/60 hover:bg-zinc-900/30 transition-colors
                                ${editingId === item.id ? "bg-blue-950/10" : ""}`}
                            >
                              {/* 1. 번역 데이터 고유 ID */}
                              <td className="p-4 font-mono text-zinc-500 font-bold">
                                {item.id}
                              </td>
                              
                              {/* 2. 티커 (영문 모노체 스타일링) */}
                              <td className="p-4 font-mono font-bold text-slate-300 tracking-wider">
                                {item.ticker}
                              </td>
                              
                              {/* 3. 한국어 이름 셀 (인라인 에디터) */}
                              <td className="p-4">
                                {editingId === item.id ? (
                                  <input
                                    type="text"
                                    value={editingName}
                                    onChange={(e) => setEditingName(e.target.value)}
                                    className="bg-[#05080f] border border-blue-500/50 rounded-lg px-3 py-1 text-xs text-slate-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") handleUpdateTranslation(item.id);
                                      if (e.key === "Escape") setEditingId(null);
                                    }}
                                    autoFocus
                                  />
                                ) : (
                                  <span className="text-slate-100 font-medium">
                                    {item.name_ko}
                                  </span>
                                )}
                              </td>
                              
                              {/* 4. 작업 액션 버튼셋 */}
                              <td className="p-4 text-right">
                                <div className="flex items-center justify-end space-x-2">
                                  {editingId === item.id ? (
                                    <>
                                      <button
                                        onClick={() => handleUpdateTranslation(item.id)}
                                        className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors cursor-pointer"
                                        title="저장"
                                      >
                                        <Check className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={() => setEditingId(null)}
                                        className="p-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors cursor-pointer"
                                        title="취소"
                                      >
                                        <X className="w-3.5 h-3.5" />
                                      </button>
                                    </>
                                  ) : (
                                    <>
                                      <button
                                        onClick={() => startEditTranslation(item)}
                                        className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors cursor-pointer"
                                        title="수정"
                                      >
                                        <Edit2 className="w-3.5 h-3.5" />
                                      </button>
                                      <button
                                        onClick={() => handleDeleteTranslation(item.id, item.ticker)}
                                        className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 transition-colors cursor-pointer"
                                        title="삭제"
                                      >
                                        <Trash2 className="w-3.5 h-3.5" />
                                      </button>
                                    </>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>

                      {/* Premium Dark-mode Pagination Controller */}
                      {totalPages > 1 && (
                        <div className="flex flex-col sm:flex-row items-center justify-between border-t border-zinc-800/80 pt-5 mt-4 gap-4">
                          <span className="text-xs text-zinc-500 font-semibold">
                            Showing <strong className="text-zinc-300">{indexOfFirstItem + 1}</strong> to <strong className="text-zinc-300">{Math.min(indexOfLastItem, filteredTranslations.length)}</strong> of <strong className="text-zinc-300">{filteredTranslations.length}</strong> items
                          </span>
                          
                          <div className="flex items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                              disabled={currentPage === 1}
                              className="px-3 py-2 rounded-xl text-[10px] font-bold border border-zinc-800 bg-[#0a0f1d] hover:bg-zinc-800/60 disabled:opacity-40 disabled:hover:bg-[#0a0f1d] text-zinc-400 hover:text-white transition-all cursor-pointer"
                            >
                              Previous
                            </button>
                            
                            {Array.from({ length: totalPages }, (_, i) => i + 1)
                              .filter(page => {
                                return (
                                  page === 1 ||
                                  page === totalPages ||
                                  Math.abs(page - currentPage) <= 1
                                );
                              })
                              .map((page, idx, arr) => {
                                const showEllipsisBefore = page > 1 && arr[idx - 1] !== page - 1;
                                return (
                                  <React.Fragment key={page}>
                                    {showEllipsisBefore && (
                                      <span className="text-zinc-600 px-1 text-xs">...</span>
                                    )}
                                    <button
                                      type="button"
                                      onClick={() => setCurrentPage(page)}
                                      className={`w-8 h-8 rounded-xl text-[10px] font-bold transition-all flex items-center justify-center cursor-pointer
                                        ${currentPage === page
                                          ? "bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-lg shadow-teal-950/20 border border-teal-500/20"
                                          : "border border-zinc-800 bg-[#0a0f1d] hover:bg-zinc-800/60 text-zinc-400 hover:text-white"
                                        }`}
                                    >
                                      {page}
                                    </button>
                                  </React.Fragment>
                                );
                              })}
                              
                            <button
                              type="button"
                              onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                              disabled={currentPage === totalPages}
                              className="px-3 py-2 rounded-xl text-[10px] font-bold border border-zinc-800 bg-[#0a0f1d] hover:bg-zinc-800/60 disabled:opacity-40 disabled:hover:bg-[#0a0f1d] text-zinc-400 hover:text-white transition-all cursor-pointer"
                            >
                              Next
                            </button>
                          </div>
                        </div>
                      )}
                    </>
                  );
                })()}
              </div>
            </div>
            
            {/* 도움말 가이드 */}
            <div className="bg-gradient-to-br from-blue-950/10 to-zinc-900/40 rounded-2xl border border-blue-900/20 p-5 space-y-2 shadow-md">
              <div className="flex items-center gap-2 text-blue-400">
                <HelpCircle className="w-4 h-4" />
                <span className="text-[10px] font-bold uppercase tracking-wider">i18n 해외주식 한글 치환 원리</span>
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                해외 주식 Ticker명(예: AAPL)을 한국어명(예: 애플)으로 변환해 주는 로컬 캐싱 시스템입니다.
                사용자가 등록하거나 수정한 내용은 실시간으로 **백엔드 DB**에 반영되며, 백엔드 서버의 **RAM 캐시와 즉각 핫싱크(Hot-sync)**되어 0ms에 준하는 극도로 빠른 응답 속도를 자랑합니다.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ========================================================================= */}
      {/* 위험 영역: 모의투자 잔고 초기화 2중 확인 모달                             */}
      {/* ========================================================================= */}
      {showResetModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <div className="bg-zinc-900 border border-red-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center gap-3 mb-4 text-red-400">
              <AlertTriangle className="w-8 h-8 text-red-500" />
              <h3 className="text-lg font-extrabold">🚨 가상 계좌 자산 초기화</h3>
            </div>
            <p className="text-zinc-300 text-xs leading-relaxed mb-6">
              정말로 모의투자 계좌를 초기화하시겠습니까? 
              <br />
              현재 보유 중인 모든 **가상 주식 잔고**가 소멸되며, **거래 로그 및 봇 활동 기록**이 즉각 영구 삭제됩니다. 
              작업 완료 후 가상 예수금은 최초 금액인 **`10,000,000원 (1,000만 원)`** 상태로 깨끗이 원복됩니다.
            </p>
            <div className="flex justify-end gap-3 text-xs">
              <button 
                onClick={() => setShowResetModal(false)}
                disabled={isDangerActionLoading}
                className="px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white rounded-xl transition-colors font-semibold cursor-pointer"
              >
                취소
              </button>
              <button 
                onClick={handleResetBalance}
                disabled={isDangerActionLoading}
                className="px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors font-bold cursor-pointer flex items-center gap-1.5"
              >
                {isDangerActionLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                예, 잔고 완전히 포맷
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* 위험 영역: 보유 주식 전량 일괄 강제 청산 2중 확인 모달                     */}
      {/* ========================================================================= */}
      {showLiquidateModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <div className="bg-zinc-900 border border-red-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center gap-3 mb-4 text-red-400">
              <AlertTriangle className="w-8 h-8 text-red-500" />
              <h3 className="text-lg font-extrabold">🚨 보유 주식 전량 비상 청산</h3>
            </div>
            <p className="text-zinc-300 text-xs leading-relaxed mb-6">
              정말로 보유 중인 모든 종목을 **즉각 일괄 시장가 매도 청산**하시겠습니까?
              <br />
              이 명령을 내리면 현재 보유 잔고에 기록된 모든 티커들이 실시간 시세를 기준으로 전량 자동 매도되어 예수금 현금 계좌로 즉각 환원됩니다. 
              <br />
              <span className="text-red-400 font-bold">※ 실전(REAL) 모드인 경우 실제 증권사 매도 체결이 발생합니다.</span>
            </p>
            <div className="flex justify-end gap-3 text-xs">
              <button 
                onClick={() => setShowLiquidateModal(false)}
                disabled={isDangerActionLoading}
                className="px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white rounded-xl transition-colors font-semibold cursor-pointer"
              >
                취소
              </button>
              <button 
                onClick={handleForceLiquidate}
                disabled={isDangerActionLoading}
                className="px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors font-bold cursor-pointer flex items-center gap-1.5"
              >
                {isDangerActionLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                예, 즉시 시장가 일괄 청산
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================================= */}
      {/* Real Mode Warning Modal                                                 */}
      {/* ========================================================================= */}
      {showRealWarning && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50 px-4">
          <div className="bg-zinc-900 border border-red-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-center gap-3 mb-4 text-red-500">
              <AlertTriangle className="w-8 h-8" />
              <h3 className="text-xl font-bold">DANGER: REAL MODE</h3>
            </div>
            <p className="text-zinc-300 text-xs leading-relaxed mb-6">
              실전 거래(<strong className="text-red-400">REAL</strong>) 모드로 설정을 변경하려고 합니다. 
              이 모드에서는 입력하신 API Key를 바탕으로 <strong className="text-red-400">실제 금액(진짜 돈)</strong>으로 매매가 체결됩니다.
              계속 진행하시겠습니까?
            </p>
            <div className="flex justify-end gap-3 text-xs">
              <button 
                onClick={() => setShowRealWarning(false)}
                className="px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 text-white rounded-xl transition-colors font-medium cursor-pointer"
              >
                취소
              </button>
              <button 
                onClick={() => handleSave(true)}
                className="px-4 py-2.5 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-colors font-semibold cursor-pointer"
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
