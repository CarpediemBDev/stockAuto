"use client";

import React, { useState, useEffect } from "react";
import { 
  Globe, 
  Key, 
  Users, 
  ShieldAlert, 
  Plus, 
  Search, 
  Edit2, 
  Trash2, 
  Check, 
  X, 
  Loader2, 
  HelpCircle 
} from "lucide-react";
import { translationAPI } from "@/lib/api";
import { getErrorMessage } from "@/lib/utils";
import { toast } from "sonner";

interface TranslationItem {
  id: number;
  ticker: string;
  name_ko: string;
}

export default function AdminPage() {
  // --- 확장성 있는 사이드바 탭 메뉴 상태 관리 ---
  const [activeTab, setActiveTab] = useState<string>("translation");

  // --- 다국어 번역 사전(Translation) 상태 관리 ---
  const [translations, setTranslations] = useState<TranslationItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [searchQuery, setSearchQuery] = useState<string>("");

  // 페이징 처리 상태 관리 (페이지 당 10개 레코드 출력)
  const [currentPage, setCurrentPage] = useState<number>(1);
  const itemsPerPage = 10;

  // 검색 쿼리가 변경되면 즉시 첫 페이지로 리셋하여 엉뚱한 페이지 공백 현상 방지
  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery]);

  // 신규 등록 폼 상태
  const [newTicker, setNewTicker] = useState<string>("");
  const [newNameKo, setNewNameKo] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // 인라인 수정용 상태 (어떤 ID의 레코드를 수정 중인가)
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingName, setEditingName] = useState<string>("");

  // 사이드바 메뉴 리스트 (추후 확장성 100% 확보)
  const menuItems = [
    { id: "translation", label: "🌐 Translation Manager", icon: Globe, enabled: true },
    { id: "access_logs", label: "🔑 Access Logs", icon: Key, enabled: false },
    { id: "users", label: "👥 User Management", icon: Users, enabled: false },
    { id: "system", label: "📡 System Health", icon: ShieldAlert, enabled: false },
  ];

  // 번역 사전 데이터 불러오기
  const fetchTranslations = async () => {
    setLoading(true);
    try {
      const res = await translationAPI.getAll();
      setTranslations(res.data);
    } catch (error) {
      const msg = getErrorMessage(error);
      toast.error(`사전 데이터 로드 실패: ${msg}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "translation") {
      fetchTranslations();
    }
  }, [activeTab]);

  // 새로운 번역 신규 저장
  const handleCreate = async (e: React.FormEvent) => {
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
      fetchTranslations();
    } catch (error) {
      toast.error(`번역 등록 실패: ${getErrorMessage(error)}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // 인라인 에디팅 시작
  const startEdit = (item: TranslationItem) => {
    setEditingId(item.id);
    setEditingName(item.name_ko);
  };

  // 인라인 에디팅 저장
  const handleUpdate = async (id: number) => {
    const nameClean = editingName.trim();
    if (!nameClean) {
      toast.warning("한국어 이름을 입력해 주세요.");
      return;
    }

    try {
      await translationAPI.update(id, nameClean);
      toast.success("번역이 수정되었으며 백엔드 캐시가 즉시 동기화되었습니다!");
      setEditingId(null);
      fetchTranslations();
    } catch (error) {
      toast.error(`수정 실패: ${getErrorMessage(error)}`);
    }
  };

  // 번역 데이터 삭제
  const handleDelete = async (id: number, ticker: string) => {
    if (!confirm(`${ticker} 번역 매핑을 정말 삭제하시겠습니까?\n삭제 즉시 메모리 캐시에서도 분리됩니다.`)) {
      return;
    }

    try {
      await translationAPI.delete(id);
      toast.success(`${ticker} 번역 매핑이 성공적으로 제거되었습니다.`);
      fetchTranslations();
    } catch (error) {
      toast.error(`삭제 실패: ${getErrorMessage(error)}`);
    }
  };

  // 실시간 타이핑 필터 필터링 결과 계산
  const filteredTranslations = translations.filter(
    (t) =>
      t.ticker.toLowerCase().includes(searchQuery.toLowerCase()) ||
      t.name_ko.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 py-8 px-4 sm:px-6 lg:px-8">
      <div className="max-w-[1400px] mx-auto">
        
        {/* 헤더 섹션 */}
        <div className="mb-8 border-b border-zinc-800 pb-5">
          <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-zinc-200 via-slate-100 to-zinc-400 bg-clip-text text-transparent">
            ⚙️ System Administration
          </h1>
          <p className="mt-2 text-sm text-zinc-400">
            StockAuto 트레이딩 시스템 및 플랫폼의 기준 정보와 정책을 관리하는 마스터 어드민 패널입니다.
          </p>
        </div>

        {/* 메인 2열 그리드 레이아웃 (확장성 확보) */}
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          
          {/* 좌측 사이드바 메뉴 (Side Navigation Bar) */}
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
            
            {/* 도움말 가이드 */}
            <div className="bg-gradient-to-br from-blue-950/20 to-zinc-900/40 rounded-2xl border border-blue-900/20 p-5 space-y-3 shadow-md">
              <div className="flex items-center gap-2 text-blue-400">
                <HelpCircle size={18} />
                <span className="text-xs font-bold uppercase tracking-wider">i18n 캐싱 시스템 원리</span>
              </div>
              <p className="text-[11px] text-zinc-400 leading-relaxed">
                종목 사전에 저장된 한글명들은 <strong>서버 기동 시(Startup)</strong> 백엔드 RAM 메모리로 로드되어 <strong>0ms 속도</strong>로 서빙됩니다. 사용자가 추가/수정하는 즉시 백엔드 RAM 캐시와 DB 테이블이 완벽히 동기화됩니다.
              </p>
            </div>
          </div>

          {/* 우측 메인 콘텐츠 패널 (Content Dynamic Panel) */}
          <div className="lg:col-span-3 space-y-6">
            
            {/* 🌐 1. 다국어 종목 번역 사전 관리 패널 */}
            {activeTab === "translation" && (
              <div className="space-y-6">
                
                {/* A. 새로운 번역 등록 인라인 폼 */}
                <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
                  <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
                    <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                      <Plus size={18} className="text-blue-400" />
                      신규 주식 한글명 커스텀 등록
                    </h2>
                    <span className="text-[10px] text-zinc-400 font-semibold bg-zinc-800 px-2 py-0.5 rounded">
                      AUTO SYNC ACTIVE
                    </span>
                  </div>
                  
                  <form onSubmit={handleCreate} className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
                    <div>
                      <label className="block text-xs text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">
                        미국 주식 Ticker (영어)
                      </label>
                      <input
                        type="text"
                        placeholder="예: TSLA"
                        value={newTicker}
                        onChange={(e) => setNewTicker(e.target.value)}
                        className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 tracking-widest font-mono uppercase"
                        disabled={isSubmitting}
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-zinc-400 font-semibold mb-1.5 uppercase tracking-wider">
                        한국어 치환 이름 (한글)
                      </label>
                      <input
                        type="text"
                        placeholder="예: 테슬라"
                        value={newNameKo}
                        onChange={(e) => setNewNameKo(e.target.value)}
                        className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl px-4 py-2.5 text-sm text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                        disabled={isSubmitting}
                      />
                    </div>
                    <button
                      type="submit"
                      disabled={isSubmitting}
                      className="w-full bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white font-bold text-sm py-2.5 px-4 rounded-xl shadow-lg shadow-indigo-950/20 hover:scale-[1.01] active:scale-[0.99] transition-all flex items-center justify-center gap-2"
                    >
                      {isSubmitting ? (
                        <>
                          <Loader2 size={16} className="animate-spin" />
                          등록 중...
                        </>
                      ) : (
                        "번역 사전에 즉시 등록"
                      )}
                    </button>
                  </form>
                </div>

                {/* B. 데이터 테이블 필터 및 조회 영역 */}
                <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-zinc-800 pb-4">
                    <div>
                      <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
                        <Globe size={18} className="text-emerald-400" />
                        주식 한글화 기준정보 데이터 목록
                      </h2>
                      <p className="text-xs text-zinc-400 mt-1">
                        전체 사전에 저장된 번역 데이터 수: <strong className="text-emerald-400">{translations.length}개</strong>
                      </p>
                    </div>
                    
                    {/* 실시간 필터 인풋 필드 */}
                    <div className="relative max-w-xs w-full">
                      <Search size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" />
                      <input
                        type="text"
                        placeholder="티커 또는 한글명 검색..."
                        value={searchQuery}
                        onChange={(e) => setSearchQuery(e.target.value)}
                        className="w-full bg-[#0a0f1d] border border-zinc-800 rounded-xl pl-10 pr-4 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-emerald-500"
                      />
                    </div>
                  </div>

                  {/* C. 대망의 데이터 그리드 테이블 */}
                  <div className="overflow-x-auto">
                    {loading ? (
                      <div className="py-20 flex flex-col items-center justify-center gap-3">
                        <Loader2 size={36} className="animate-spin text-zinc-500" />
                        <span className="text-xs text-zinc-500 font-semibold">데이터베이스 로딩 중...</span>
                      </div>
                    ) : filteredTranslations.length === 0 ? (
                      <div className="py-16 text-center">
                        <Globe size={48} className="mx-auto text-zinc-700 mb-3" />
                        <p className="text-sm font-semibold text-zinc-500">등록되었거나 검색 조건에 부합하는 데이터가 없습니다.</p>
                        <p className="text-xs text-zinc-600 mt-1">상단 폼을 이용하여 첫 번역 주식을 등록해 보세요!</p>
                      </div>
                    ) : (() => {
                      // 페이징 계산식 실행
                      const totalPages = Math.ceil(filteredTranslations.length / itemsPerPage);
                      const indexOfLastItem = currentPage * itemsPerPage;
                      const indexOfFirstItem = indexOfLastItem - itemsPerPage;
                      const currentItems = filteredTranslations.slice(indexOfFirstItem, indexOfLastItem);
                      
                      return (
                        <>
                          <table className="min-w-full divide-y divide-zinc-800/60">
                            <thead>
                              <tr className="text-left text-xs uppercase text-zinc-500 font-bold tracking-wider">
                                <th className="px-6 py-3.5">ID</th>
                                <th className="px-6 py-3.5">Ticker (티커)</th>
                                <th className="px-6 py-3.5">Korean Name (한글 이름)</th>
                                <th className="px-6 py-3.5 text-right">Actions (작업)</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-zinc-800/40 text-sm">
                              {currentItems.map((item) => (
                                <tr 
                                  key={item.id} 
                                  className={`transition-colors duration-150 hover:bg-zinc-800/10 
                                    ${editingId === item.id ? "bg-blue-950/10" : ""}`}
                                >
                                  {/* 1. 번역 데이터 고유 ID */}
                                  <td className="px-6 py-4 text-xs font-mono text-zinc-500 font-bold">
                                    {item.id}
                                  </td>
                                  
                                  {/* 2. 티커 (영문 모노체 스타일링) */}
                                  <td className="px-6 py-4 font-mono font-bold text-slate-300 tracking-wider">
                                    {item.ticker}
                                  </td>
                                  
                                  {/* 3. 한국어 이름 셀 (인라인 에디터 변신 기믹!) */}
                                  <td className="px-6 py-4">
                                    {editingId === item.id ? (
                                      <input
                                        type="text"
                                        value={editingName}
                                        onChange={(e) => setEditingName(e.target.value)}
                                        className="bg-[#05080f] border border-blue-500/50 rounded-lg px-3 py-1 text-sm text-slate-100 focus:outline-none focus:ring-1 focus:ring-blue-500"
                                        onKeyDown={(e) => {
                                          if (e.key === "Enter") handleUpdate(item.id);
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
                                  
                                  {/* 4. 작업 액션 버튼셋 (수정/삭제/저장/취소) */}
                                  <td className="px-6 py-4 text-right space-x-2">
                                    {editingId === item.id ? (
                                      <>
                                        <button
                                          onClick={() => handleUpdate(item.id)}
                                          className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-colors"
                                          title="저장"
                                        >
                                          <Check size={16} />
                                        </button>
                                        <button
                                          onClick={() => setEditingId(null)}
                                          className="p-1.5 rounded-lg bg-zinc-800 text-zinc-400 hover:bg-zinc-700 transition-colors"
                                          title="취소"
                                        >
                                          <X size={16} />
                                        </button>
                                      </>
                                    ) : (
                                      <>
                                        <button
                                          onClick={() => startEdit(item)}
                                          className="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                                          title="수정"
                                        >
                                          <Edit2 size={16} />
                                        </button>
                                        <button
                                          onClick={() => handleDelete(item.id, item.ticker)}
                                          className="p-1.5 rounded-lg bg-rose-500/10 text-rose-400 hover:bg-rose-500/20 transition-colors"
                                          title="삭제"
                                        >
                                          <Trash2 size={16} />
                                        </button>
                                      </>
                                    )}
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
                                  className="px-3 py-2 rounded-xl text-xs font-bold border border-zinc-800 bg-[#0a0f1d] hover:bg-zinc-800/60 disabled:opacity-40 disabled:hover:bg-[#0a0f1d] text-zinc-400 hover:text-white transition-all"
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
                                          className={`w-9 h-9 rounded-xl text-xs font-bold transition-all flex items-center justify-center
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
                                  className="px-3 py-2 rounded-xl text-xs font-bold border border-zinc-800 bg-[#0a0f1d] hover:bg-zinc-800/60 disabled:opacity-40 disabled:hover:bg-[#0a0f1d] text-zinc-400 hover:text-white transition-all"
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

              </div>
            )}
            
            {/* 추후 다른 어드민 탭 활성화 시 렌더링될 플레이스홀더들 */}
            {activeTab !== "translation" && (
              <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-12 text-center shadow-xl">
                <Loader2 size={48} className="mx-auto text-zinc-600 mb-4 animate-pulse" />
                <h3 className="text-lg font-bold text-slate-300">메뉴 오픈 예정</h3>
                <p className="text-sm text-zinc-500 mt-2">
                  선택하신 &apos;{menuItems.find(m => m.id === activeTab)?.label}&apos; 메뉴는 추후 시스템 고도화 시 연동될 예정입니다.
                </p>
              </div>
            )}

          </div>

        </div>

      </div>
    </div>
  );
}
