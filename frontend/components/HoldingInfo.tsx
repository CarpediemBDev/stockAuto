"use client";

import React from "react";
import { Activity, ExternalLink, Newspaper, Ruler, SearchX } from "lucide-react";
import { useTranslations } from "next-intl";

import { getProfitColor } from "@/lib/theme";
import { cn, formatUsdAs } from "@/lib/utils";
import { harvestLevels, type HarvestLevelInput } from "@/lib/holdingLevels";
import { ScoreBreakdown, type ScoreCardFactor } from "@/components/ScoreBreakdown";

/** 보유 카드가 이미 들고 있는 값만 쓴다. 이 모달을 열어도 추가 조회는 일어나지 않는다. */
export interface HoldingInfoTarget extends HarvestLevelInput {
  avg_price: number;
  fx_rate?: number;
  management?: "BOT_OWNED" | "EXTERNAL" | "DELEGATED";
  harvest_enabled?: boolean;
  risk_basis_price?: number | null;
}

/** /scanner/latest의 신호 한 건 중 이 모달이 쓰는 필드. */
export interface HoldingScanSignal {
  signal_score: number;
  score_card?: ScoreCardFactor[];
  news_sentiment?: "POSITIVE" | "NEGATIVE" | "NEUTRAL";
  news_sentiment_score?: number;
  news_summary?: string;
  news_url?: string;
}

/** 기준가가 현재가에서 몇 % 떨어져 있는지. 현재가가 기준 아래면 음수다. */
function distancePct(current: number, level: number): number | null {
  return level > 0 ? ((current - level) / level) * 100 : null;
}

/**
 * 보유 종목 하나의 정보: ① 스캐너 점수 ② AI 뉴스 ③ 가격 기준선.
 *
 * ①②는 스캐너 캐시(/scanner/latest)에서 온다. 그 응답은 시장 상위 10개와 관심종목만 담기 때문에
 * 보유 종목이 빠져 있는 경우가 흔하다. 그때는 빈 칸으로 두지 않고 "스캔 결과에 없다"고 밝힌다 -
 * 비어 있으면 점수가 0이거나 데이터가 사라진 것으로 읽힌다.
 * ③은 카드와 같은 출처(브로커 잔고 + 보유분 상태)라 항상 있다.
 */
export function HoldingInfo({
  holding,
  signal,
  displayCurrency = "KRW",
}: {
  holding: HoldingInfoTarget;
  signal: HoldingScanSignal | null;
  displayCurrency?: "KRW" | "USD";
}) {
  const t = useTranslations("components");
  const money = (usd: number) => formatUsdAs(usd, displayCurrency, holding.fx_rate);

  // 카드와 같은 폴백 규칙을 쓴다. 카드와 모달의 현재가가 다르면 같은 수익률을 두고 두 숫자가 생긴다.
  const current = holding.current_price !== undefined ? holding.current_price : holding.avg_price * 1.02;
  const { armPrice, stopPrice, floorPrice, noSellZone } = harvestLevels(holding);
  const showHarvest = holding.management === "EXTERNAL" && !!holding.harvest_enabled;

  const levels: { key: string; label: string; price: number; pct: number | null }[] = [
    { key: "avg", label: t("portfolio.avg_price"), price: holding.avg_price, pct: distancePct(current, holding.avg_price) },
    { key: "peak", label: t("portfolio.info_peak"), price: holding.highest_price, pct: distancePct(current, holding.highest_price) },
  ];
  // 위임분의 손절선은 매수가가 아니라 이 값을 기준으로 잡힌다. 평단가만 보면 "왜 아직 안 팔지"가 된다.
  if (holding.management === "DELEGATED" && holding.risk_basis_price != null) {
    levels.push({
      key: "basis",
      label: t("portfolio.info_risk_basis"),
      price: holding.risk_basis_price,
      pct: distancePct(current, holding.risk_basis_price),
    });
  }
  if (showHarvest && armPrice != null) {
    levels.push({ key: "arm", label: t("portfolio.info_harvest_arm"), price: armPrice, pct: distancePct(current, armPrice) });
  }
  if (showHarvest && stopPrice != null) {
    levels.push({ key: "stop", label: t("portfolio.info_harvest_stop"), price: stopPrice, pct: distancePct(current, stopPrice) });
  }
  // 기준선을 이탈해도 이 가격 이하에서는 팔지 않는다. 기준선만 보여주면 그 선에서 팔린다고 오해한다.
  if (showHarvest && floorPrice != null) {
    levels.push({ key: "floor", label: t("portfolio.info_harvest_floor"), price: floorPrice, pct: distancePct(current, floorPrice) });
  }

  const sentiment = signal?.news_sentiment;
  const sentimentScore = signal?.news_sentiment_score ?? 50;

  return (
    <div className="flex flex-col gap-5 text-sm">
      {/* ③ 가격 기준선 - 항상 있는 정보라 맨 위에 둔다 */}
      <section className="flex flex-col gap-2">
        <h4 className="flex items-center gap-1.5 text-xs font-bold text-slate-200">
          <Ruler size={14} className="text-indigo-400" />
          {t("portfolio.info_levels_title")}
        </h4>
        <div className="rounded-xl border border-zinc-800 divide-y divide-zinc-800/70">
          <div className="flex justify-between items-baseline px-3 py-2">
            <span className="text-zinc-400 text-xs font-semibold">{t("portfolio.info_current_price")}</span>
            <span className="font-mono font-bold text-slate-100">{money(current)}</span>
          </div>
          {levels.map((level) => (
            <div key={level.key} className="flex justify-between items-baseline px-3 py-2">
              <span className="text-zinc-500 text-xs">{level.label}</span>
              <span className="font-mono text-slate-300 text-xs">
                {money(level.price)}
                {level.pct != null && (
                  <span className={cn("ml-2 text-[11px]", getProfitColor(level.pct))}>
                    {t("portfolio.info_vs_current", { pct: `${level.pct >= 0 ? "+" : ""}${level.pct.toFixed(2)}%` })}
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
        {showHarvest && noSellZone && (
          <p className="text-[11px] text-amber-400/90 leading-relaxed">{t("portfolio.harvest_no_sell_zone")}</p>
        )}
        <p className="text-[11px] text-zinc-600 leading-relaxed">{t("portfolio.info_levels_hint")}</p>
      </section>

      {!signal ? (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 text-center">
          <SearchX className="text-zinc-600 mx-auto mb-2" size={24} />
          <p className="text-xs font-bold text-slate-300">{t("portfolio.info_not_scanned_title")}</p>
          <p className="text-[11px] text-zinc-500 mt-1.5 leading-relaxed">{t("portfolio.info_not_scanned_hint")}</p>
        </div>
      ) : (
        <>
          {/* ① 스캐너 점수 */}
          <section className="flex flex-col gap-2">
            <h4 className="flex items-center gap-1.5 text-xs font-bold text-slate-200">
              <Activity size={14} className="text-indigo-400" />
              {t("portfolio.info_score_title")}
            </h4>
            <ScoreBreakdown score={signal.signal_score} scoreCard={signal.score_card} />
          </section>

          {/* ② AI 뉴스 */}
          <section className="flex flex-col gap-2">
            <h4 className="flex items-center gap-1.5 text-xs font-bold text-slate-200">
              <Newspaper size={14} className="text-indigo-400" />
              {t("portfolio.info_news_title")}
            </h4>
            {signal.news_summary ? (
              <>
                <div className="bg-surface-card-subtle p-4 rounded-xl border border-zinc-800 shadow-inner">
                  <div className="flex justify-between items-center text-[10px] text-zinc-500 font-extrabold tracking-wide mb-2.5">
                    <span>BEARISH 📉</span>
                    <span className="text-xs font-black text-white font-mono flex items-center gap-1.5">
                      {t("common.sentiment_label")}
                      <span className={cn(
                        "px-1.5 py-0.5 rounded text-[10px] font-mono",
                        sentimentScore >= 60 ? "bg-emerald-500/10 text-emerald-400" :
                        sentimentScore <= 40 ? "bg-rose-500/10 text-rose-400" :
                        "bg-zinc-800 text-zinc-400"
                      )}>
                        {sentimentScore}%
                      </span>
                    </span>
                    <span>BULLISH 📈</span>
                  </div>
                  <div className="relative w-full h-1.5 bg-gradient-to-r from-rose-500/70 via-amber-400/70 to-emerald-500/70 rounded-full border border-zinc-900 shadow-inner">
                    <div
                      className="absolute w-3 h-3 -top-0.5 bg-white rounded-full border border-zinc-950 -translate-x-1/2 shadow-[0_0_12px_rgba(255,255,255,0.9)]"
                      style={{ left: `${sentimentScore}%` }}
                    />
                  </div>
                </div>
                <div className="bg-surface-card-subtle/90 border border-zinc-800 p-4 rounded-xl flex flex-col gap-3">
                  <span className={cn(
                    "self-start text-[9px] font-black px-2 py-0.5 rounded border tracking-widest",
                    sentiment === "POSITIVE" ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/20" :
                    sentiment === "NEGATIVE" ? "bg-rose-500/10 text-rose-400 border-rose-500/20" :
                    "bg-zinc-500/10 text-zinc-400 border-zinc-800"
                  )}>
                    {sentiment ?? "NEUTRAL"}
                  </span>
                  <p className="pl-4 border-l-2 border-indigo-500/30 text-xs text-zinc-300 font-semibold leading-relaxed tracking-wide">
                    {signal.news_summary}
                  </p>
                  {signal.news_url && (
                    <a
                      href={signal.news_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="self-end flex items-center gap-1.5 text-[10px] text-indigo-400 hover:text-indigo-300 transition-colors font-black uppercase tracking-widest"
                    >
                      {t("common.read_article")}
                      <ExternalLink size={11} />
                    </a>
                  )}
                </div>
              </>
            ) : (
              <p className="text-[11px] text-zinc-500 rounded-xl border border-zinc-800 p-3">{t("portfolio.info_no_news")}</p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
