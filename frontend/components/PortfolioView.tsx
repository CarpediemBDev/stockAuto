'use client';

import React, { useState } from 'react';
import {
  Target, MessageSquare, ExternalLink,
  TrendingUp, TrendingDown, Newspaper, ArrowUpRight, ArrowDownRight, Info, ShieldAlert
} from 'lucide-react';
import useSWR from 'swr';
import { pollInterval } from '@/lib/sse';
import { fetcher } from '@/lib/api';
import { cn, usdToKrw, formatKrw } from '@/lib/utils';
import { getProfitColor } from '@/lib/theme';
import { Modal } from '@/components/ui';
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

  const selectedNews = activeNewsItem?.news;
  const isPositive = selectedNews?.sentiment === 'POSITIVE';
  const isNegative = selectedNews?.sentiment === 'NEGATIVE';

  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {holdings.map((h) => {
          const cleanTicker = h.ticker.replace(/^[A-Z0-9]+_/, "");
          const strategyLabel = h.strategy_name || h.strategy_type?.replaceAll("_", " ") || "";
          const strategyBadgeClass = "bg-indigo-500/15 text-indigo-400 border-indigo-500/30";

          const currentPrice = h.current_price !== undefined ? h.current_price : h.avg_price * 1.02;
          const profitRate = h.avg_price > 0 ? ((currentPrice - h.avg_price) / h.avg_price) * 100 : 0;
          const dropFromPeak = h.highest_price > 0 ? ((currentPrice - h.highest_price) / h.highest_price) * 100 : 0;
          const news = newsMap[cleanTicker];
          const isProfitable = profitRate >= 0;

          return (
            <div key={h.id} className="bg-surface-card/80 backdrop-blur-xl border border-zinc-800/80 rounded-2xl p-5 hover:border-zinc-700 transition-all group flex flex-col h-full shadow-lg">
              <div className="flex justify-between items-start mb-4">
                <div className="min-w-0 flex-1 mr-3">
                  <h4 className="text-xs font-bold text-zinc-400 tracking-wider uppercase flex items-center gap-1.5 flex-wrap">
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
