'use client';

import React, { useRef, useState } from 'react';
import {
  Target, MessageSquare, ExternalLink,
  TrendingUp, TrendingDown, Newspaper, ArrowUpRight, ArrowDownRight, Info, ShieldAlert, Sprout,
  SlidersHorizontal, HandCoins
} from 'lucide-react';
import useSWR, { mutate as globalMutate } from 'swr';
import { pollInterval } from '@/lib/sse';
import { fetcher, accountAPI } from '@/lib/api';
import { cn, usdToKrw, formatKrw } from '@/lib/utils';
import { getProfitColor } from '@/lib/theme';
import { Modal } from '@/components/ui';
import { useTranslations } from "next-intl";
import { useStrategyCatalog } from "@/hooks/useStrategyCatalog";

interface Holding {
  id: number;
  ticker: string;
  ticker_name: string;
  avg_price: number;
  quantity: number;
  highest_price: number;
  current_price?: number;
  is_mock?: boolean;
  provider?: string;
  fx_rate?: number;
  strategy_type?: string;
  strategy_name?: string;
  /**
   * 봇 관할권.
   *  - BOT_OWNED: 봇이 산 포지션
   *  - EXTERNAL: 봇이 사지 않은 보유분. 매도·추가매수 대상이 아니다
   *  - DELEGATED: 사용자가 봇에 넘긴 보유분. 봇 규칙을 그대로 받되 원장은 분리된다
   */
  management?: "BOT_OWNED" | "EXTERNAL" | "DELEGATED";
  /** 수확 모드 - EXTERNAL 전용 opt-in. 급등 후 고점 이탈 시에만 자동 매도한다. */
  harvest_enabled?: boolean;
  /** 급등 임계를 넘겨 추적이 시작됐는지. 무장 전에는 아무 동작도 하지 않는다. */
  harvest_armed?: boolean;
  observed_base_price?: number | null;
  /** 방어 경보 - EXTERNAL 전용 opt-in. 기본값에서는 알림만 보내고 매도는 하지 않는다. */
  guard_enabled?: boolean;
  /** 방어 조건 충족 시 동작. 기본 ALERT_ONLY. LIQUIDATE만 실제로 매도한다. */
  guard_action?: 'ALERT_ONLY' | 'SHADOW' | 'LIQUIDATE';
  guard_sell_ratio?: number;
  /** 매도 대상 지정용 슬라이스 목록. id는 브로커마다 의미가 달라 키로 쓸 수 없다. */
  slices?: { strategy_type: string; management: string; quantity: number; risk_basis_price?: number | null }[];
  /** 위임 시점가. 위임분의 손절선은 매수가가 아니라 이 값을 기준으로 잡힌다. */
  risk_basis_price?: number | null;
}

/** 서버가 confirm=false 프리뷰로 돌려주는 예상 결과. 이 값을 보여준 뒤에만 실제 매도를 보낸다. */
interface SellPreview {
  ticker: string;
  ticker_name: string;
  strategy_type?: string;
  management?: "BOT_OWNED" | "EXTERNAL" | "DELEGATED";
  held_quantity: number;
  sell_quantity: number;
  estimated_price: number;
  estimated_proceeds: number;
  estimated_realized_pnl: number;
  estimated_return_rate: number;
}

interface NewsInfo {
  sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  sentiment_score: number;
  summary: string;
  url?: string;
}

const PortfolioView = ({ displayCurrency = "KRW" }: { displayCurrency?: "KRW" | "USD" }) => {
  const t = useTranslations("components");
  const [activeNewsItem, setActiveNewsItem] = useState<{ ticker: string; name: string; news: NewsInfo } | null>(null);

  // 매도는 되돌릴 수 없으므로 2단계다 - 먼저 서버 프리뷰를 받아 보여주고, 사용자가 확인 버튼을
  // 누르면 그때 실제 주문이 나간다. pendingTicker는 중복 탭 가드를 겸한다.
  const [sellPreview, setSellPreview] = useState<SellPreview | null>(null);
  const [pendingTicker, setPendingTicker] = useState<string | null>(null);
  const [sellError, setSellError] = useState<string | null>(null);
  const [sellResult, setSellResult] = useState<string | null>(null);

  // ⚠️ 중복 요청 가드는 반드시 ref여야 한다. state로 막으면 setState가 리렌더 뒤에야
  //    disabled를 걸기 때문에, 같은 틱에 들어온 두 번째·세 번째 탭이 전부 통과한다
  //    (모바일 더블탭·고스트 클릭에서 실제로 재현된다 — stock-auto-mobile 세션 보고).
  //    서버의 사용자·심볼 주문 락은 두 번째 요청에 409를 돌려줄 뿐 요청 자체를 막지 못하고,
  //    수량을 지정한 매도라면 첫 요청이 끝난 뒤 도착한 두 번째가 그대로 또 체결될 수 있다.
  const inFlightRef = useRef(false);

  /** 동기 래치. 이미 진행 중이면 false를 돌려주고, 아니면 래치를 걸고 true를 준다. */
  const acquireLatch = () => {
    if (inFlightRef.current) return false;
    inFlightRef.current = true;
    return true;
  };
  const releaseLatch = () => {
    inFlightRef.current = false;
  };

  const [togglingTicker, setTogglingTicker] = useState<string | null>(null);
  // 위임 스위치는 카드 푸터가 아니라 전용 모달에서 다룬다. 방어를 켜면 조치 모드 3개가
  // 더 붙어 버튼이 6개가 되는데, 415px 카드 한 줄에 넣으면 글자가 줄바꿈되어 읽을 수 없다.
  const [delegationTarget, setDelegationTarget] = useState<Holding | null>(null);
  // 위임할 전략 슬롯. 카탈로그가 오기 전에는 비어 있고, 사용자가 고르면 채워진다.
  const [delegateSlot, setDelegateSlot] = useState<string>("");
  const { strategies } = useStrategyCatalog();

  const toggleSwitch = async (
    h: Holding,
    patch: {
      harvest_enabled?: boolean;
      guard_enabled?: boolean;
      guard_action?: 'ALERT_ONLY' | 'SHADOW' | 'LIQUIDATE';
      guard_sell_ratio?: number;
    },
    failKey: string,
  ) => {
    const cleanTicker = h.ticker.replace(/^[A-Z0-9]+_/, "");
    if (!acquireLatch()) return;
    setTogglingTicker(cleanTicker);
    setSellError(null);
    try {
      await accountAPI.updateHoldingManagement(cleanTicker, {
        strategy_type: h.strategy_type,
        ...patch,
      });
      globalMutate('/account/holdings');
    } catch (err) {
      const detail = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setSellError(detail?.message || detail?.detail || t(failKey));
    } finally {
      setTogglingTicker(null);
      releaseLatch();
    }
  };

  // 관할권 이전. 스위치와 달리 되돌릴 수 있는 값 하나가 아니라 리스크 기준가·고점·
  // 추가매수 단계를 함께 재설정하므로 전용 엔드포인트를 쓴다.
  const changeDelegation = async (h: Holding, action: 'DELEGATE' | 'REVOKE') => {
    const cleanTicker = h.ticker.replace(/^[A-Z0-9]+_/, "");
    if (action === 'DELEGATE' && !delegateSlot) {
      setSellError(t("portfolio.delegate_slot_required"));
      return;
    }
    if (!acquireLatch()) return;
    setTogglingTicker(cleanTicker);
    setSellError(null);
    try {
      await accountAPI.changeHoldingDelegation(cleanTicker, {
        action,
        strategy_type: h.strategy_type,
        ...(action === 'DELEGATE' ? { delegate_slot: delegateSlot } : {}),
      });
      globalMutate('/account/holdings');
      setDelegationTarget(null);
    } catch (err) {
      const detail = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setSellError(detail?.message || detail?.detail || t("portfolio.delegation_change_failed"));
    } finally {
      setTogglingTicker(null);
      releaseLatch();
    }
  };

  const requestSellPreview = async (h: Holding) => {
    if (!acquireLatch()) return;
    const cleanTicker = h.ticker.replace(/^[A-Z0-9]+_/, "");
    setPendingTicker(cleanTicker);
    setSellError(null);
    setSellResult(null);
    try {
      const res = await accountAPI.previewSellHolding(cleanTicker, { strategy_type: h.strategy_type });
      setSellPreview((res.data?.data ?? res.data) as SellPreview);
    } catch (err) {
      const detail = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setSellError(detail?.message || detail?.detail || t("portfolio.sell_failed"));
    } finally {
      setPendingTicker(null);
      releaseLatch();
    }
  };

  const confirmSell = async () => {
    if (!sellPreview) return;
    if (!acquireLatch()) return;
    setPendingTicker(sellPreview.ticker);
    setSellError(null);
    try {
      const res = await accountAPI.sellHolding(sellPreview.ticker, {
        quantity: sellPreview.sell_quantity,
        strategy_type: sellPreview.strategy_type,
      });
      const body = (res.data?.data ?? res.data) as { message?: string };
      setSellResult(body?.message || t("portfolio.sell_done"));
      setSellPreview(null);
      globalMutate('/account/holdings');
      globalMutate('/account/balance');
    } catch (err) {
      const detail = (err as { response?: { data?: { message?: string; detail?: string } } })?.response?.data;
      setSellError(detail?.message || detail?.detail || t("portfolio.sell_failed"));
    } finally {
      setPendingTicker(null);
      releaseLatch();
    }
  };

  const { data: holdingsData, isLoading } = useSWR('/account/holdings', fetcher, { refreshInterval: pollInterval(15000) });
  const holdings: Holding[] = holdingsData || [];

  const { data: scannerData } = useSWR('/scanner/latest', fetcher, { refreshInterval: pollInterval(60000) });

  const newsMap = React.useMemo(() => {
    const map: Record<string, NewsInfo> = {};
    const signals = scannerData ? (Array.isArray(scannerData) ? scannerData : (scannerData.signals || [])) : [];
    for (const item of signals) {
      if (item.news_summary && item.news_sentiment) {
        map[item.ticker] = {
          sentiment: item.news_sentiment,
          sentiment_score: item.news_sentiment_score ?? 50,
          summary: item.news_summary,
          url: item.news_url,
        };
      }
    }
    return map;
  }, [scannerData]);

  if (isLoading) return <div className="text-zinc-500 text-sm p-8 text-center animate-pulse">Loading portfolio...</div>;

  if (holdings.length === 0) {
    return (
      <div className="bg-surface-card/60 border border-zinc-800/80 rounded-2xl p-12 text-center">
        <div className="w-16 h-16 bg-zinc-800/60 rounded-full flex items-center justify-center mx-auto mb-4">
          <Target className="text-zinc-500" size={32} />
        </div>
        <h3 className="text-lg font-bold text-slate-300">{t("portfolio.empty_title")}</h3>
        <p className="text-zinc-500 text-sm mt-2">{t("portfolio.empty_hint")}</p>
      </div>
    );
  }

  // 모달은 스냅샷이 아니라 폴링 최신값을 따라가야 한다. 열어둔 종목이 목록에서 사라지면 닫는다.
  const delegationHolding = delegationTarget
    ? holdings.find(
        (x) => x.ticker === delegationTarget.ticker && x.strategy_type === delegationTarget.strategy_type,
      ) ?? null
    : null;

  const selectedNews = activeNewsItem?.news;
  const isPositive = selectedNews?.sentiment === 'POSITIVE';
  const isNegative = selectedNews?.sentiment === 'NEGATIVE';

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {holdings.map((h) => {
          const cleanTicker = h.ticker.replace(/^[A-Z0-9]+_/, "");
          const isExternal = h.management === "EXTERNAL";
          const isDelegated = h.management === "DELEGATED";
          const strategyLabel = h.strategy_name || h.strategy_type?.replaceAll("_", " ") || "";
          // 봇이 건드리지 않는 보유분은 전략 뱃지와 색을 달리해, 자동 매도를 기대하지 않도록 구분한다.
          const strategyBadgeClass = isExternal
            ? "bg-zinc-500/15 text-zinc-400 border-zinc-500/30"
            : "bg-indigo-500/15 text-indigo-400 border-indigo-500/30";

          const currentPrice = h.current_price !== undefined ? h.current_price : h.avg_price * 1.02;
          const profitRate = h.avg_price > 0 ? ((currentPrice - h.avg_price) / h.avg_price) * 100 : 0;
          const dropFromPeak = h.highest_price > 0 ? ((currentPrice - h.highest_price) / h.highest_price) * 100 : 0;
          const news = newsMap[cleanTicker];
          const isProfitable = profitRate >= 0;

          return (
            // key로 h.id를 쓰면 안 된다 - KIS 경로의 id는 목록 순번이라 한 종목이 청산되면
            // 나머지 행의 id가 전부 밀리고, Toss 경로는 id가 없다. (ticker, strategy_type)이
            // 브로커 무관하게 안정적인 키다(DB 유니크 제약과 동일).
            <div key={`${h.ticker}:${h.strategy_type ?? ''}`} className="bg-surface-card/80 backdrop-blur-xl border border-zinc-800/80 rounded-2xl p-5 hover:border-zinc-700 transition-all group flex flex-col h-full shadow-lg">
              <div className="flex justify-between items-start mb-4">
                <div className="min-w-0 flex-1 mr-3">
                  <h4 className="text-xs font-bold text-zinc-400 tracking-wider uppercase flex items-center gap-1.5 flex-wrap">
                    {cleanTicker}
                    {/* EXTERNAL은 서버가 strategy_name을 "봇 관리 안 함"으로 치환해 내려주므로
                        아래 전용 배지와 문구가 겹친다. 관할권 표시는 전용 배지 하나로만 한다. */}
                    {strategyLabel && !isExternal && (
                      <span className={`text-[8px] font-black px-1.5 py-0.5 rounded border tracking-wider uppercase ${strategyBadgeClass}`}>
                        {strategyLabel}
                      </span>
                    )}
                    {isExternal && (
                      <span
                        className="text-[8px] font-black px-1.5 py-0.5 rounded border tracking-wider uppercase bg-slate-500/15 text-slate-300 border-slate-500/30"
                        title={t("portfolio.external_badge_tip")}
                      >
                        {t("portfolio.external_badge")}
                      </span>
                    )}
                    {/* 위임분은 전략 배지와 함께 뜬다. 어느 전략에 맡겼는지가 사용자가
                        알아야 할 정보이고, 관할권이 넘어갔다는 사실은 이 배지가 알린다. */}
                    {isDelegated && (
                      <span
                        className="text-[8px] font-black px-1.5 py-0.5 rounded border tracking-wider uppercase bg-amber-500/15 text-amber-400 border-amber-500/30"
                        title={t("portfolio.delegated_badge_tip")}
                      >
                        {t("portfolio.delegated_badge")}
                      </span>
                    )}
                    {/* 켜진 위임 스위치는 배지로만 알린다. 조작은 위임 설정 모달에서 한다. */}
                    {isExternal && h.harvest_enabled && (
                      <span className="text-[8px] font-black px-1.5 py-0.5 rounded border tracking-wider uppercase bg-emerald-500/15 text-emerald-400 border-emerald-500/30">
                        {h.harvest_armed ? t("portfolio.harvest_armed_label") : t("portfolio.harvest_on")}
                      </span>
                    )}
                    {isExternal && h.guard_enabled && (
                      <span className={cn(
                        "text-[8px] font-black px-1.5 py-0.5 rounded border tracking-wider uppercase",
                        h.guard_action === "LIQUIDATE"
                          ? "bg-rose-500/15 text-rose-400 border-rose-500/30"
                          : "bg-sky-500/15 text-sky-400 border-sky-500/30"
                      )}>
                        {h.guard_action === "LIQUIDATE"
                          ? t("portfolio.guard_action_liquidate")
                          : h.guard_action === "SHADOW"
                            ? t("portfolio.guard_action_shadow")
                            : t("portfolio.guard_on")}
                      </span>
                    )}
                    <span className={`text-[8px] font-black px-1 py-0.5 rounded border tracking-wider uppercase ${
                      h.is_mock === false
                        ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                        : "bg-amber-500/15 text-amber-400 border-amber-500/30"
                    }`}>
                      {h.provider || (h.is_mock === false ? "Live" : "Mock")}
                    </span>
                  </h4>
                  <div className="flex items-baseline gap-2 mt-0.5">
                    <h3 className="text-base font-bold text-slate-100 truncate">{h.ticker_name}</h3>
                    <span className={`text-xs font-bold font-mono shrink-0 ${getProfitColor(profitRate)}`}>
                      {displayCurrency === "USD"
                        ? `$${currentPrice.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                        : formatKrw(usdToKrw(currentPrice, h.fx_rate))
                      }
                    </span>
                  </div>

                  {/* 뉴스 마퀴 — 스캐너에서 뉴스 있을 때만 표시 */}
                  {news && (
                    <button
                      onClick={() => setActiveNewsItem({ ticker: cleanTicker, name: h.ticker_name, news })}
                      className="mt-1.5 overflow-hidden w-full text-left cursor-pointer"
                      title={t("common.news_click")}
                    >
                      <div className={cn(
                        'flex items-center gap-1 text-[9px] font-bold',
                        news.sentiment === 'POSITIVE' ? 'text-emerald-400' :
                        news.sentiment === 'NEGATIVE' ? 'text-rose-400' :
                        'text-sky-400'
                      )}>
                        {news.sentiment === 'POSITIVE' ? (
                          <TrendingUp size={8} className="shrink-0" />
                        ) : news.sentiment === 'NEGATIVE' ? (
                          <TrendingDown size={8} className="shrink-0" />
                        ) : (
                          <Newspaper size={8} className="shrink-0" />
                        )}
                        <span className="overflow-hidden flex-1">
                          <span className="portfolio-news-ticker opacity-75 hover:opacity-100">
                            {news.summary}
                          </span>
                        </span>
                      </div>
                    </button>
                  )}
                </div>
                <div className={`flex items-center shrink-0 px-2 py-1 rounded text-xs font-bold ${getProfitColor(profitRate, { badge: true })}`}>
                  {isProfitable ? <ArrowUpRight size={14} className="mr-1" /> : <ArrowDownRight size={14} className="mr-1" />}
                  {profitRate.toFixed(2)}%
                </div>
              </div>

              <div className="space-y-4 flex flex-col flex-grow justify-between">
                <div>
                  {/* 핵심 투자 지표 */}
                  <div className="grid grid-cols-2 gap-2 p-3 bg-surface-card-subtle/70 rounded-xl border border-zinc-800/60 text-xs">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-zinc-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.avg_price")}</span>
                      <span className="text-slate-200 font-mono font-medium">
                        {displayCurrency === "USD"
                          ? `$${h.avg_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                          : formatKrw(usdToKrw(h.avg_price, h.fx_rate))
                        }
                      </span>
                    </div>
                    <div className="flex flex-col gap-0.5 text-right">
                      <span className="text-zinc-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.quantity")}</span>
                      <span className="text-slate-200 font-mono font-medium">{h.quantity.toLocaleString()}{t("common.shares_suffix")}</span>
                    </div>
                    <div className="flex flex-col gap-0.5 mt-1.5 pt-1.5 border-t border-zinc-800/60">
                      <span className="text-zinc-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.principal")}</span>
                      <span className="text-zinc-400 font-mono font-medium">
                        {displayCurrency === "USD"
                          ? `$${(h.avg_price * h.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : formatKrw(usdToKrw(h.avg_price * h.quantity, h.fx_rate))
                        }
                      </span>
                    </div>
                    <div className="flex flex-col gap-0.5 text-right mt-1.5 pt-1.5 border-t border-zinc-800/60">
                      <span className="text-zinc-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.market_value")}</span>
                      <span className={`font-mono font-bold ${getProfitColor(profitRate)}`}>
                        {displayCurrency === "USD"
                          ? `$${(currentPrice * h.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : formatKrw(usdToKrw(currentPrice * h.quantity, h.fx_rate))
                        }
                      </span>
                    </div>
                  </div>

                  {/* 고점 대비 하락 게이지 */}
                  <div className="space-y-1.5 mt-4">
                    <div className="flex justify-between text-[10px] font-bold tracking-tight">
                      <span className="group/drop relative inline-flex items-center gap-1 cursor-help text-zinc-500 w-fit">
                        <span>{t("portfolio.drop_from_peak")}</span>
                        <Info size={10} className="text-zinc-600 group-hover/drop:text-zinc-400 transition-colors" />
                        <span className="pointer-events-none absolute bottom-full left-0 mb-2 w-64 scale-95 opacity-0 group-hover/drop:scale-100 group-hover/drop:opacity-100 transition-all duration-200 bg-zinc-950 text-slate-300 text-[10px] font-normal normal-case leading-relaxed p-3 rounded-xl shadow-2xl border border-zinc-800 z-50 text-left whitespace-normal">
                          {t("portfolio.drop_tip_intro")}<b>{t("portfolio.drop_tip_peak")}</b>{t("portfolio.drop_tip_rest")}<br/><br/>
                          <span className="text-rose-400">{t("portfolio.drop_tip_minus")}</span>{t("portfolio.drop_tip_minus_desc")}<br/>
                          <span className="text-emerald-400">{t("portfolio.drop_tip_plus")}</span>{t("portfolio.drop_tip_plus_desc")}
                        </span>
                      </span>
                      <span className={dropFromPeak < -5 ? 'text-amber-500' : 'text-zinc-400'}>
                        {dropFromPeak.toFixed(2)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-500 ${dropFromPeak < -5 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                        style={{ width: `${Math.max(0, Math.min(100, (1 - Math.abs(dropFromPeak)/10) * 100))}%` }}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-zinc-800/60 mt-6">
                  <div className="flex flex-col">
                    <span className="group/tip relative inline-flex items-center gap-1 cursor-help text-[10px] text-zinc-500 uppercase select-none w-fit">
                      <span>{t("portfolio.peak")}</span>
                      <Info size={10} className="text-zinc-600 group-hover/tip:text-zinc-400 transition-colors" />
                      <span className="pointer-events-none absolute bottom-full left-0 mb-2 w-64 scale-95 opacity-0 group-hover/tip:scale-100 group-hover/tip:opacity-100 transition-all duration-200 bg-zinc-950 text-zinc-400 text-[9px] font-normal normal-case leading-relaxed p-2.5 rounded-lg shadow-2xl border border-zinc-800 z-50 text-left whitespace-normal">
                        {t("portfolio.peak_tip")}
                      </span>
                    </span>
                    <span className="text-sm font-bold text-slate-300">
                      {displayCurrency === "USD"
                        ? `$${h.highest_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                        : formatKrw(usdToKrw(h.highest_price, h.fx_rate))
                      }
                    </span>
                  </div>
                  <div className="flex items-center gap-3">
                    {(isExternal || isDelegated) && (
                      <button
                        type="button"
                        onClick={() => { setDelegateSlot(""); setDelegationTarget(h); }}
                        className="flex items-center gap-1 text-[10px] font-bold px-2 py-1 rounded-lg border border-zinc-700 text-zinc-400 hover:bg-zinc-800 transition-colors"
                      >
                        <SlidersHorizontal size={12} />
                        {t("portfolio.delegation_settings")}
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => requestSellPreview(h)}
                      disabled={pendingTicker !== null}
                      className="text-[11px] font-bold px-2.5 py-1 rounded-lg border border-rose-500/40 text-rose-400 hover:bg-rose-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                    >
                      {t("portfolio.sell_action")}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 봇 위임 설정 모달 — 스위치와 조치 모드를 카드 밖으로 뺀다 */}
      <Modal
        isOpen={!!delegationHolding}
        onClose={() => { if (!togglingTicker) setDelegationTarget(null); }}
        maxWidth="sm"
        title={
          <div className="flex items-center gap-2">
            <SlidersHorizontal size={18} className="text-zinc-400" />
            <span className="font-bold">{t("portfolio.delegation_title")}</span>
          </div>
        }
      >
        {delegationHolding && (
          <div className="space-y-5 text-sm">
            <p className="text-zinc-500 text-xs leading-relaxed">
              {t("portfolio.delegation_intro", { ticker: delegationHolding.ticker.replace(/^[A-Z0-9]+_/, "") })}
            </p>

            {/* 관할권 이전 — 스위치보다 위에 둔다. 위임하면 아래 스위치는 의미가 없어진다. */}
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3 space-y-2">
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5 font-bold text-slate-200">
                  <HandCoins size={14} className="text-amber-400" />
                  {t("portfolio.delegate_title")}
                </span>
                {delegationHolding.management === "DELEGATED" ? (
                  <button
                    type="button"
                    onClick={() => changeDelegation(delegationHolding, "REVOKE")}
                    disabled={togglingTicker !== null}
                    className="text-[11px] font-bold px-2.5 py-1 rounded-lg border border-amber-500/40 text-amber-400 hover:bg-amber-500/10 disabled:opacity-40 shrink-0"
                  >
                    {t("portfolio.delegate_revoke")}
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => changeDelegation(delegationHolding, "DELEGATE")}
                    disabled={togglingTicker !== null || !delegateSlot}
                    className="text-[11px] font-bold px-2.5 py-1 rounded-lg border border-amber-500/40 text-amber-400 hover:bg-amber-500/10 disabled:opacity-40 shrink-0"
                  >
                    {t("portfolio.delegate_action")}
                  </button>
                )}
              </div>
              {delegationHolding.management === "DELEGATED" ? (
                <p className="text-[11px] text-zinc-500 leading-relaxed">
                  {t("portfolio.delegate_active_tip", {
                    strategy: delegationHolding.strategy_name || delegationHolding.strategy_type || "",
                    price: delegationHolding.risk_basis_price != null
                      ? `$${delegationHolding.risk_basis_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                      : "-",
                  })}
                </p>
              ) : (
                <>
                  <select
                    value={delegateSlot}
                    onChange={(e) => setDelegateSlot(e.target.value)}
                    disabled={togglingTicker !== null}
                    className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-2 py-1.5 text-[11px] text-slate-200 disabled:opacity-40"
                  >
                    <option value="">{t("portfolio.delegate_slot_placeholder")}</option>
                    {(strategies || []).map((strategy) => (
                      <option key={strategy.id} value={strategy.id}>{strategy.name}</option>
                    ))}
                  </select>
                  <p className="text-[11px] text-zinc-500 leading-relaxed">
                    {t("portfolio.delegate_tip")}
                  </p>
                </>
              )}
            </div>

            {/* 수확 */}
            <div className={cn(
              "rounded-xl border border-zinc-800 p-3 space-y-2",
              delegationHolding.management === "DELEGATED" && "opacity-40 pointer-events-none",
            )}>
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5 font-bold text-slate-200">
                  <Sprout size={14} className="text-emerald-400" />
                  {t("portfolio.harvest_title")}
                </span>
                <button
                  type="button"
                  onClick={() => toggleSwitch(delegationHolding, { harvest_enabled: !delegationHolding.harvest_enabled }, "portfolio.harvest_toggle_failed")}
                  disabled={togglingTicker !== null}
                  className={cn(
                    "text-[11px] font-bold px-2.5 py-1 rounded-lg border transition-colors disabled:opacity-40 shrink-0",
                    delegationHolding.harvest_enabled
                      ? "border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/10"
                      : "border-zinc-700 text-zinc-500 hover:bg-zinc-800"
                  )}
                >
                  {delegationHolding.harvest_enabled
                    ? (delegationHolding.harvest_armed ? t("portfolio.harvest_armed_label") : t("portfolio.harvest_on"))
                    : t("portfolio.harvest_off")}
                </button>
              </div>
              <p className="text-[11px] text-zinc-500 leading-relaxed">
                {delegationHolding.harvest_armed ? t("portfolio.harvest_armed_tip") : t("portfolio.harvest_tip")}
              </p>
            </div>

            {/* 방어 */}
            <div className={cn(
              "rounded-xl border border-zinc-800 p-3 space-y-2",
              delegationHolding.management === "DELEGATED" && "opacity-40 pointer-events-none",
            )}>
              <div className="flex items-center justify-between gap-3">
                <span className="flex items-center gap-1.5 font-bold text-slate-200">
                  <ShieldAlert size={14} className="text-sky-400" />
                  {t("portfolio.guard_title")}
                </span>
                <button
                  type="button"
                  onClick={() => toggleSwitch(delegationHolding, { guard_enabled: !delegationHolding.guard_enabled }, "portfolio.guard_toggle_failed")}
                  disabled={togglingTicker !== null}
                  className={cn(
                    "text-[11px] font-bold px-2.5 py-1 rounded-lg border transition-colors disabled:opacity-40 shrink-0",
                    delegationHolding.guard_enabled
                      ? "border-sky-500/40 text-sky-400 hover:bg-sky-500/10"
                      : "border-zinc-700 text-zinc-500 hover:bg-zinc-800"
                  )}
                >
                  {delegationHolding.guard_enabled ? t("portfolio.guard_on") : t("portfolio.guard_off")}
                </button>
              </div>
              <p className="text-[11px] text-zinc-500 leading-relaxed">{t("portfolio.guard_tip")}</p>

              {delegationHolding.guard_enabled && (
                <div className="pt-2 mt-1 border-t border-zinc-800/70 space-y-2">
                  <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">
                    {t("portfolio.guard_action_label")}
                  </span>
                  <div className="grid grid-cols-3 gap-1.5">
                    {(["ALERT_ONLY", "SHADOW", "LIQUIDATE"] as const).map((mode) => {
                      const active = (delegationHolding.guard_action || "ALERT_ONLY") === mode;
                      const label =
                        mode === "ALERT_ONLY" ? t("portfolio.guard_action_alert_only")
                        : mode === "SHADOW" ? t("portfolio.guard_action_shadow")
                        : t("portfolio.guard_action_liquidate");
                      return (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => toggleSwitch(delegationHolding, { guard_action: mode }, "portfolio.guard_toggle_failed")}
                          disabled={togglingTicker !== null}
                          className={cn(
                            "text-[10px] font-bold px-1.5 py-1.5 rounded-lg border transition-colors disabled:opacity-40 leading-tight",
                            active
                              ? (mode === "LIQUIDATE"
                                  ? "border-rose-500/50 text-rose-400 bg-rose-500/10"
                                  : "border-sky-500/40 text-sky-400 bg-sky-500/10")
                              : "border-zinc-800 text-zinc-600 hover:bg-zinc-800"
                          )}
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  <p className="text-[11px] text-zinc-500 leading-relaxed">{t("portfolio.guard_action_tip")}</p>

                  {/* 조치가 실제로 나가기까지의 조건을 미리 알린다. 모르면 모드를 바꿔놓고
                      "왜 안 팔리지?"가 된다 — 스트릭이 0부터 다시 쌓이기 때문이다. */}
                  <p className="text-[11px] text-zinc-600 leading-relaxed">
                    {t("portfolio.guard_streak_notice")}
                  </p>

                  {delegationHolding.guard_action === "LIQUIDATE" && (
                    <div className="space-y-2 pt-2 mt-1 border-t border-zinc-800/70">
                      <span className="text-[10px] uppercase tracking-wider font-bold text-zinc-500">
                        {t("portfolio.guard_sell_ratio_label")}
                      </span>
                      <div className="grid grid-cols-4 gap-1.5">
                        {[0.25, 0.5, 0.75, 1].map((ratio) => {
                          const active = Math.abs((delegationHolding.guard_sell_ratio ?? 0.5) - ratio) < 0.001;
                          return (
                            <button
                              key={ratio}
                              type="button"
                              onClick={() => toggleSwitch(delegationHolding, { guard_sell_ratio: ratio }, "portfolio.guard_toggle_failed")}
                              disabled={togglingTicker !== null}
                              className={cn(
                                "text-[11px] font-bold px-1.5 py-1.5 rounded-lg border transition-colors disabled:opacity-40",
                                active
                                  ? "border-rose-500/50 text-rose-400 bg-rose-500/10"
                                  : "border-zinc-800 text-zinc-600 hover:bg-zinc-800"
                              )}
                            >
                              {Math.round(ratio * 100)}%
                            </button>
                          );
                        })}
                      </div>
                      <p className="text-[11px] text-rose-400 leading-relaxed">
                        {t("portfolio.guard_action_warning")}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>

            {sellError && <p className="text-[11px] text-rose-400">{sellError}</p>}
          </div>
        )}
      </Modal>

      {/* 개별 매도 확인 모달 — 서버 프리뷰를 그대로 보여주고, 확인해야 주문이 나간다 */}
      <Modal
        isOpen={!!sellPreview}
        onClose={() => { if (!pendingTicker) setSellPreview(null); }}
        maxWidth="sm"
        title={
          <div className="flex items-center gap-2 text-rose-400">
            <ShieldAlert size={18} />
            <span className="font-bold">{t("portfolio.sell_confirm_title")}</span>
          </div>
        }
      >
        {sellPreview && (
          <div className="space-y-4 text-sm">
            <p className="text-zinc-400 leading-relaxed">
              {t("portfolio.sell_confirm_body", {
                ticker: sellPreview.ticker,
                quantity: sellPreview.sell_quantity,
              })}
            </p>
            <div className="rounded-xl border border-zinc-800 divide-y divide-zinc-800/70">
              {[
                [t("portfolio.sell_est_price"), `$${sellPreview.estimated_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`],
                [t("portfolio.sell_est_proceeds"), `$${sellPreview.estimated_proceeds.toLocaleString(undefined, { minimumFractionDigits: 2 })}`],
                [t("portfolio.sell_est_pnl"), `$${sellPreview.estimated_realized_pnl.toLocaleString(undefined, { minimumFractionDigits: 2 })} (${sellPreview.estimated_return_rate.toFixed(2)}%)`],
              ].map(([label, value]) => (
                <div key={label} className="flex justify-between px-3 py-2">
                  <span className="text-zinc-500 text-xs">{label}</span>
                  <span className="font-mono text-slate-200">{value}</span>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-amber-500/90">{t("portfolio.sell_irreversible")}</p>
            {sellError && <p className="text-[11px] text-rose-400">{sellError}</p>}
            <div className="flex gap-2 justify-end pt-1">
              <button
                type="button"
                onClick={() => setSellPreview(null)}
                disabled={pendingTicker !== null}
                className="px-3 py-1.5 text-xs font-bold rounded-lg border border-zinc-700 text-zinc-400 hover:bg-zinc-800 disabled:opacity-40"
              >
                {t("portfolio.sell_cancel")}
              </button>
              <button
                type="button"
                onClick={confirmSell}
                disabled={pendingTicker !== null}
                className="px-3 py-1.5 text-xs font-bold rounded-lg bg-rose-600 text-white hover:bg-rose-500 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {pendingTicker ? t("portfolio.sell_pending") : t("portfolio.sell_confirm_action")}
              </button>
            </div>
          </div>
        )}
      </Modal>

      {(sellResult || (sellError && !sellPreview)) && (
        <div className={cn(
          "mt-4 text-xs rounded-lg border px-3 py-2",
          sellResult ? "border-emerald-500/30 text-emerald-400" : "border-rose-500/30 text-rose-400"
        )}>
          {sellResult || sellError}
        </div>
      )}

      {/* AI 뉴스 분석 모달 */}
      <Modal
        isOpen={!!activeNewsItem}
        onClose={() => setActiveNewsItem(null)}
        maxWidth="lg"
        title={
          activeNewsItem && (
            <div className="flex items-center gap-3">
              <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">
                <MessageSquare size={18} />
              </div>
              <div>
                <h3 className="text-sm font-black text-white tracking-wide uppercase">AI Sentiment & Signals</h3>
                <p className="text-[10px] text-zinc-500 font-mono tracking-wider mt-0.5">
                  {activeNewsItem.name} ({activeNewsItem.ticker})
                </p>
              </div>
            </div>
          )
        }
      >
        {selectedNews && (
          <div className="flex flex-col gap-4">
            {/* 뉴스 심리 스펙트럼 */}
            <div className="bg-surface-card-subtle p-4 rounded-xl border border-zinc-800 shadow-inner">
              <div className="flex justify-between items-center text-[10px] text-zinc-500 font-extrabold tracking-wide mb-2.5">
                <span>BEARISH 📉</span>
                <span className="text-xs font-black text-white font-mono flex items-center gap-1.5">
                  {t("common.sentiment_label")}
                  <span className={cn(
                    'px-1.5 py-0.5 rounded text-[10px] font-mono',
                    selectedNews.sentiment_score >= 60 ? 'bg-emerald-500/10 text-emerald-400' :
                    selectedNews.sentiment_score <= 40 ? 'bg-rose-500/10 text-rose-400' :
                    'bg-zinc-800 text-zinc-400'
                  )}>
                    {selectedNews.sentiment_score}%
                  </span>
                </span>
                <span>BULLISH 📈</span>
              </div>
              <div className="relative w-full h-1.5 bg-gradient-to-r from-rose-500/70 via-amber-400/70 to-emerald-500/70 rounded-full border border-zinc-900 shadow-inner">
                <div
                  className="absolute w-3 h-3 -top-0.5 bg-white rounded-full border border-zinc-950 -translate-x-1/2 shadow-[0_0_12px_rgba(255,255,255,0.9)] animate-pulse transition-all duration-1000 ease-out"
                  style={{ left: `${selectedNews.sentiment_score}%` }}
                />
              </div>
            </div>

            {/* AI 요약 */}
            <div className="bg-surface-card-subtle/90 border border-zinc-800 p-5 rounded-xl shadow-inner flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className={cn(
                  'text-[9px] font-black px-2 py-0.5 rounded border tracking-widest',
                  isPositive ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                  isNegative ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' :
                  'bg-zinc-500/10 text-zinc-400 border-zinc-800'
                )}>
                  {selectedNews.sentiment}
                </span>
                <span className="text-[9px] text-zinc-500 font-bold font-mono tracking-wider">AI REAL-TIME ANALYSIS</span>
              </div>
              <div className="relative pl-4 border-l-2 border-indigo-500/30">
                <p className="text-xs text-zinc-300 font-semibold leading-relaxed tracking-wide">
                  {selectedNews.summary}
                </p>
              </div>
              {selectedNews.url && (
                <a
                  href={selectedNews.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="self-end flex items-center gap-1.5 text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors font-black uppercase tracking-widest group/link"
                >
                  {t("common.read_article")}
                  <ExternalLink size={11} className="group-hover/link:translate-x-0.5 group-hover/link:-translate-y-0.5 transition-transform" />
                </a>
              )}
            </div>

            <div className="flex justify-end pt-2">
              <button
                onClick={() => setActiveNewsItem(null)}
                className="px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-xl text-xs font-bold transition-all active:scale-95 border border-zinc-700/40 cursor-pointer"
              >
                {t("common.close")}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  );
};

export default PortfolioView;
