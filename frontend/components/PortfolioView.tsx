'use client';

import React, { useState } from 'react';
import {
  Target, MessageSquare, ExternalLink, X,
  TrendingUp, TrendingDown, Newspaper, ArrowUpRight, ArrowDownRight, Info, ShieldAlert
} from 'lucide-react';
import useSWR from 'swr';
import { pollInterval } from '@/lib/sse';
import { fetcher } from '@/lib/api';
import { cn, usdToKrw, formatKrw } from '@/lib/utils';
import { useTranslations } from "next-intl";

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
}

interface NewsInfo {
  sentiment: 'POSITIVE' | 'NEGATIVE' | 'NEUTRAL';
  sentiment_score: number;
  summary: string;
  url?: string;
}

// 뉴스 모달 컴포넌트
function NewsModal({
  ticker,
  name,
  news,
  onClose,
}: {
  ticker: string;
  name: string;
  news: NewsInfo;
  onClose: () => void;
}) {
  const t = useTranslations("components");
  const isPositive = news.sentiment === 'POSITIVE';
  const isNegative = news.sentiment === 'NEGATIVE';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/65 backdrop-blur-sm" onClick={onClose} />
      <div className={cn(
        'relative w-full max-w-lg bg-zinc-900/97 border-2 rounded-2xl shadow-[0_25px_60px_-15px_rgba(0,0,0,0.9)] z-10 overflow-hidden',
        isPositive ? 'border-emerald-500/35 shadow-[0_0_30px_rgba(16,185,129,0.15)]' :
        isNegative ? 'border-rose-500/35 shadow-[0_0_30px_rgba(244,63,94,0.15)]' :
        'border-zinc-700'
      )}>
        {/* 상단 컬러 라인 */}
        <div className={cn(
          'absolute top-0 left-0 right-0 h-[2px] bg-gradient-to-r',
          isPositive ? 'from-emerald-500 via-teal-400 to-indigo-500' :
          isNegative ? 'from-rose-500 via-pink-400 to-purple-500' :
          'from-zinc-700 via-zinc-500 to-zinc-700'
        )} />

        {/* 헤더 */}
        <div className="flex items-center justify-between px-6 pt-6 pb-4 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-500/10 rounded-lg text-indigo-400">
              <MessageSquare size={18} />
            </div>
            <div>
              <h3 className="text-sm font-black text-white tracking-wide uppercase">AI Sentiment & Signals</h3>
              <p className="text-[10px] text-zinc-500 font-mono tracking-wider mt-0.5">
                {name} ({ticker})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-zinc-400 hover:text-white transition-all active:scale-90"
          >
            <X size={15} />
          </button>
        </div>

        <div className="p-6 flex flex-col gap-4">
          {/* 뉴스 심리 스펙트럼 */}
          <div className="bg-zinc-950/60 p-4 rounded-xl border border-zinc-800 shadow-inner">
            <div className="flex justify-between items-center text-[10px] text-zinc-500 font-extrabold tracking-wide mb-2.5">
              <span>BEARISH 📉</span>
              <span className="text-xs font-black text-white font-mono flex items-center gap-1.5">
                {t("common.sentiment_label")}
                <span className={cn(
                  'px-1.5 py-0.5 rounded text-[10px] font-mono',
                  news.sentiment_score >= 60 ? 'bg-emerald-500/10 text-emerald-400' :
                  news.sentiment_score <= 40 ? 'bg-rose-500/10 text-rose-400' :
                  'bg-zinc-800 text-zinc-400'
                )}>
                  {news.sentiment_score}%
                </span>
              </span>
              <span>BULLISH 📈</span>
            </div>
            <div className="relative w-full h-1.5 bg-gradient-to-r from-rose-500/70 via-amber-400/70 to-emerald-500/70 rounded-full border border-zinc-900 shadow-inner">
              <div
                className="absolute w-3 h-3 -top-0.5 bg-white rounded-full border border-zinc-950 -translate-x-1/2 shadow-[0_0_12px_rgba(255,255,255,0.9)] animate-pulse transition-all duration-1000 ease-out"
                style={{ left: `${news.sentiment_score}%` }}
              />
            </div>
          </div>

          {/* AI 요약 */}
          <div className="bg-gradient-to-b from-zinc-950/80 to-zinc-950/95 border border-zinc-800 p-5 rounded-xl shadow-inner flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className={cn(
                'text-[9px] font-black px-2 py-0.5 rounded border tracking-widest',
                isPositive ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                isNegative ? 'bg-rose-500/10 text-rose-400 border-rose-500/20' :
                'bg-zinc-500/10 text-zinc-400 border-zinc-800'
              )}>
                {news.sentiment}
              </span>
              <span className="text-[9px] text-zinc-500 font-bold font-mono tracking-wider">AI REAL-TIME ANALYSIS</span>
            </div>
            <div className="relative pl-4 border-l-2 border-indigo-500/30">
              <p className="text-xs text-zinc-300 font-semibold leading-relaxed tracking-wide">
                {news.summary}
              </p>
            </div>
            {news.url && (
              <a
                href={news.url}
                target="_blank"
                rel="noopener noreferrer"
                className="self-end flex items-center gap-1.5 text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors font-black uppercase tracking-widest group/link"
              >
                {t("common.read_article")}
                <ExternalLink size={11} className="group-hover/link:translate-x-0.5 group-hover/link:-translate-y-0.5 transition-transform" />
              </a>
            )}
          </div>

          <div className="flex justify-end">
            <button
              onClick={onClose}
              className="px-5 py-2 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs font-bold transition-all active:scale-95 border border-zinc-700/30"
            >
              {t("common.close")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

const PortfolioView = ({ displayCurrency = "KRW" }: { displayCurrency?: "KRW" | "USD" }) => {
  const t = useTranslations("components");
  const [activeNewsItem, setActiveNewsItem] = useState<{ ticker: string; name: string; news: NewsInfo } | null>(null);

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

  if (isLoading) return <div className="text-slate-500 text-sm p-8 text-center animate-pulse">Loading portfolio...</div>;

  if (holdings.length === 0) {
    return (
      <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-12 text-center">
        <div className="w-16 h-16 bg-slate-800 rounded-full flex items-center justify-center mx-auto mb-4">
          <Target className="text-slate-600" size={32} />
        </div>
        <h3 className="text-lg font-bold text-slate-300">{t("portfolio.empty_title")}</h3>
        <p className="text-slate-500 text-sm mt-2">{t("portfolio.empty_hint")}</p>
      </div>
    );
  }

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {holdings.map((h) => {
          const cleanTicker = h.ticker.replace(/^[A-Z0-9]+_/, "");
          const strategyLabel = h.strategy_name || h.strategy_type?.replaceAll("_", " ") || "";
          const strategyBadgeClass = "bg-blue-500/15 text-blue-400 border-blue-500/30";

          const currentPrice = h.current_price !== undefined ? h.current_price : h.avg_price * 1.02;
          const profitRate = h.avg_price > 0 ? ((currentPrice - h.avg_price) / h.avg_price) * 100 : 0;
          const dropFromPeak = h.highest_price > 0 ? ((currentPrice - h.highest_price) / h.highest_price) * 100 : 0;
          const news = newsMap[cleanTicker];

          return (
            <div key={h.id} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 hover:border-slate-700 transition-all group flex flex-col h-full">
              <div className="flex justify-between items-start mb-4">
                <div className="min-w-0 flex-1 mr-3">
                  <h4 className="text-xs font-bold text-slate-500 tracking-wider uppercase flex items-center gap-1.5 flex-wrap">
                    {cleanTicker}
                    {strategyLabel && (
                      <span className={`text-[8px] font-black px-1.5 py-0.5 rounded border tracking-wider uppercase ${strategyBadgeClass}`}>
                        {strategyLabel}
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
                    <span className={`text-xs font-bold font-mono shrink-0 ${profitRate >= 0 ? 'text-rose-400' : 'text-blue-400'}`}>
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
                      className="mt-1.5 overflow-hidden w-full text-left"
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
                <div className={`flex items-center shrink-0 px-2 py-1 rounded text-xs font-bold ${profitRate >= 0 ? 'bg-rose-500/10 text-rose-500' : 'bg-blue-500/10 text-blue-500'}`}>
                  {profitRate >= 0 ? <ArrowUpRight size={14} className="mr-1" /> : <ArrowDownRight size={14} className="mr-1" />}
                  {profitRate.toFixed(2)}%
                </div>
              </div>

              <div className="space-y-4 flex flex-col flex-grow justify-between">
                <div>
                  {/* 핵심 투자 지표 */}
                  <div className="grid grid-cols-2 gap-2 p-3 bg-slate-950/60 rounded-xl border border-slate-800/40 text-xs">
                    <div className="flex flex-col gap-0.5">
                      <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.avg_price")}</span>
                      <span className="text-slate-200 font-mono font-medium">
                        {displayCurrency === "USD"
                          ? `$${h.avg_price.toLocaleString(undefined, { minimumFractionDigits: 2 })}`
                          : formatKrw(usdToKrw(h.avg_price, h.fx_rate))
                        }
                      </span>
                    </div>
                    <div className="flex flex-col gap-0.5 text-right">
                      <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.quantity")}</span>
                      <span className="text-slate-200 font-mono font-medium">{h.quantity.toLocaleString()}{t("common.shares_suffix")}</span>
                    </div>
                    <div className="flex flex-col gap-0.5 mt-1.5 pt-1.5 border-t border-slate-800/40">
                      <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.principal")}</span>
                      <span className="text-slate-400 font-mono font-medium">
                        {displayCurrency === "USD"
                          ? `$${(h.avg_price * h.quantity).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
                          : formatKrw(usdToKrw(h.avg_price * h.quantity, h.fx_rate))
                        }
                      </span>
                    </div>
                    <div className="flex flex-col gap-0.5 text-right mt-1.5 pt-1.5 border-t border-slate-800/40">
                      <span className="text-slate-500 text-[10px] uppercase tracking-wider font-semibold">{t("portfolio.market_value")}</span>
                      <span className={`font-mono font-bold ${profitRate >= 0 ? 'text-rose-400' : 'text-blue-400'}`}>
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
                      <span className="group/drop relative inline-flex items-center gap-1 cursor-help text-slate-500 w-fit">
                        <span>{t("portfolio.drop_from_peak")}</span>
                        <Info size={10} className="text-slate-600 group-hover/drop:text-slate-400 transition-colors" />
                        <span className="pointer-events-none absolute bottom-full left-0 mb-2 w-64 scale-95 opacity-0 group-hover/drop:scale-100 group-hover/drop:opacity-100 transition-all duration-200 bg-slate-950 text-slate-300 text-[10px] font-normal normal-case leading-relaxed p-3 rounded-xl shadow-2xl border border-slate-700 z-50 text-left whitespace-normal">
                          {t("portfolio.drop_tip_intro")}<b>{t("portfolio.drop_tip_peak")}</b>{t("portfolio.drop_tip_rest")}<br/><br/>
                          <span className="text-blue-400">{t("portfolio.drop_tip_minus")}</span>{t("portfolio.drop_tip_minus_desc")}<br/>
                          <span className="text-rose-400">{t("portfolio.drop_tip_plus")}</span>{t("portfolio.drop_tip_plus_desc")}
                        </span>
                      </span>
                      <span className={dropFromPeak < -5 ? 'text-amber-500' : 'text-slate-400'}>
                        {dropFromPeak.toFixed(2)}%
                      </span>
                    </div>
                    <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-500 ${dropFromPeak < -5 ? 'bg-amber-500' : 'bg-emerald-500'}`}
                        style={{ width: `${Math.max(0, Math.min(100, (1 - Math.abs(dropFromPeak)/10) * 100))}%` }}
                      />
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-3 border-t border-slate-800/50 mt-6">
                  <div className="flex flex-col">
                    <span className="group/tip relative inline-flex items-center gap-1 cursor-help text-[10px] text-slate-500 uppercase select-none w-fit">
                      <span>{t("portfolio.peak")}</span>
                      <Info size={10} className="text-slate-600 group-hover/tip:text-slate-400 transition-colors" />
                      <span className="pointer-events-none absolute bottom-full left-0 mb-2 w-64 scale-95 opacity-0 group-hover/tip:scale-100 group-hover/tip:opacity-100 transition-all duration-200 bg-slate-950 text-slate-400 text-[9px] font-normal normal-case leading-relaxed p-2.5 rounded-lg shadow-2xl border border-slate-800 z-50 text-left whitespace-normal">
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
                  {dropFromPeak < -3 && h.highest_price > h.avg_price && (
                    <div className="flex items-center text-amber-500 animate-pulse">
                      <ShieldAlert size={16} className="mr-1" />
                      <span className="text-[11px] font-bold">{t("portfolio.dynamic_exit")}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* AI 뉴스 분석 모달 */}
      {activeNewsItem && (
        <NewsModal
          ticker={activeNewsItem.ticker}
          name={activeNewsItem.name}
          news={activeNewsItem.news}
          onClose={() => setActiveNewsItem(null)}
        />
      )}
    </>
  );
};

export default PortfolioView;
