"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

export interface ScoreCardFactor {
  factor: string;
  score: number;
  passed: boolean;
}

/**
 * 스캐너 종합 점수 게이지와 팩터별 채점표. 스캐너 표의 점수 모달과 보유 종목 정보 모달이
 * 같은 채점 결과를 보여주므로 표시는 이 컴포넌트 하나로 통일한다.
 */
export function ScoreBreakdown({ score, scoreCard }: { score: number; scoreCard?: ScoreCardFactor[] }) {
  const t = useTranslations("scanner");
  const hasCard = !!scoreCard && scoreCard.length > 0;

  return (
    <div className="flex flex-col gap-5">
      {/* 스코어 게이지바 */}
      <div className="bg-zinc-950/60 p-5 rounded-xl border border-zinc-800 shadow-inner">
        <div className="flex justify-between items-end mb-3">
          <span className="text-xs text-zinc-400 font-semibold tracking-wide">{t("overseas.total_score")}</span>
          <span className="text-3xl font-black font-mono tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-white to-zinc-400">
            {score}
            <span className="text-sm text-zinc-600 font-normal ml-1">/ 100</span>
          </span>
        </div>
        <div className="w-full h-4 bg-zinc-900 rounded-full overflow-hidden p-[2.5px] border border-zinc-850">
          <div
            className={cn(
              "h-full rounded-full transition-all duration-1000 ease-out",
              score >= 80
                ? "bg-gradient-to-r from-indigo-500 via-purple-500 to-rose-500 shadow-[0_0_16px_rgba(244,63,94,0.5)]"
                : score >= 60
                ? "bg-gradient-to-r from-indigo-500 to-amber-500 shadow-[0_0_16px_rgba(245,158,11,0.4)]"
                : "bg-indigo-500 shadow-[0_0_16px_rgba(99,102,241,0.4)]"
            )}
            style={{ width: `${score}%` }}
          />
        </div>
        {/* 점수 구간 레이블 */}
        <div className="flex justify-between mt-2 text-[11px] text-zinc-700 font-mono">
          <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
        </div>
      </div>

      {/* 팩터 칩 2열 그리드 */}
      <div className="grid grid-cols-2 gap-2">
        {hasCard ? (
          scoreCard.map((card, cidx) => (
            <div
              key={cidx}
              className={cn(
                "flex items-center justify-between px-3 py-2.5 rounded-xl text-xs border transition-all",
                card.passed
                  ? "bg-emerald-500/[0.05] border-emerald-500/20 shadow-[inset_0_1px_0_rgba(16,185,129,0.07)]"
                  : "bg-rose-500/[0.05] border-rose-500/20 shadow-[inset_0_1px_0_rgba(244,63,94,0.07)]"
              )}
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className={cn(
                  "w-1.5 h-1.5 shrink-0 rounded-full",
                  card.passed
                    ? "bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.9)]"
                    : "bg-rose-500 shadow-[0_0_6px_rgba(244,63,94,0.9)]"
                )} />
                <span className={cn("font-medium truncate", card.passed ? "text-zinc-300" : "text-zinc-500")}>
                  {card.factor}
                </span>
              </div>
              <span className={cn(
                "font-mono text-[11px] px-1.5 py-0.5 rounded font-extrabold shrink-0 ml-2",
                card.passed ? "bg-emerald-500/15 text-emerald-400" : "bg-rose-500/10 text-rose-500"
              )}>
                {card.score > 0 ? `+${card.score}` : card.score}
              </span>
            </div>
          ))
        ) : (
          <span className="col-span-2 text-xs text-zinc-600 italic text-center py-6">
            {t("overseas.no_scorecard")}
          </span>
        )}
      </div>

      {/* 합계 요약 */}
      {hasCard && (
        <div className="flex items-center justify-between px-4 py-3 bg-zinc-950/80 rounded-xl border border-zinc-800">
          <span className="text-[11px] text-zinc-500 font-semibold">
            {t("overseas.passed_count", { passed: scoreCard.filter(c => c.passed).length, total: scoreCard.length })}
          </span>
          <span className="text-[11px] font-black font-mono text-indigo-400">
            {t("overseas.sum_points", { points: scoreCard.filter(c => c.passed).reduce((s, c) => s + c.score, 0) })}
          </span>
        </div>
      )}
    </div>
  );
}
