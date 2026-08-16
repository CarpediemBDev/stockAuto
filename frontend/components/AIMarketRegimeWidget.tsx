"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { useTranslations } from "next-intl";
import { fetcher, adminAPI } from "@/lib/api";
import { Sparkles, TrendingUp, Zap, Shield, Target, CheckCircle2, Loader2, Award } from "lucide-react";
import { toast } from "sonner";
import { StrategySelectModal } from "./StrategySelectModal";
import { useStrategyCatalog, DEFAULT_STRATEGY_ID } from "@/hooks/useStrategyCatalog";
import { useMarketOverview } from "@/hooks/useMarketOverview";

export function AIMarketRegimeWidget() {
  const t = useTranslations("components");
  const { data: adminSettings, mutate: mutateSettings } = useSWR("/admin", fetcher);
  // 카탈로그 조회·타입 SSOT는 useStrategyCatalog 훅이다(중복 useSWR/타입 선언 금지).
  const { strategies } = useStrategyCatalog();
  // 시장 국면 SSOT는 /market/overview 다. 예전엔 adminSettings.market_regime을 읽었는데
  // 그 필드는 응답에 존재조차 하지 않아 폴백 "BULLISH"가 상시 표시됐고, 같은 화면의
  // 헤더·관제탑이 NEUTRAL을 가리키는 동안 위젯만 상승장이라고 주장하고 있었다.
  const { regime: currentRegime } = useMarketOverview();
  const [isApplying, setIsApplying] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // 국면을 모르는 동안에는 추천을 계산하지 않는다. 임의의 기본 국면으로 계산한 추천은
  // 근거 없는 매매 유도가 된다.
  const isRegimeReady = Boolean(currentRegime);

  // DB 카탈로그 데이터를 기반으로 하드코딩 없이 동적(Dynamic) 추천 전략 추출
  const recommendedStrategy = (() => {
    if (!currentRegime) return null;
    if (!strategies || strategies.length === 0) return null;

    // 1단계: 현재 시장 국면과 일치하거나 전천후(ALL)인 전략 필터링
    const matched = strategies.filter(
      (s) => s.regime === currentRegime || s.regime === "ALL"
    );

    if (matched.length === 0) return strategies[0];

    // 2단계: 티어 우선순위 (gold > silver > bronze > single > sandbox)에 따라 동적 1위 추출
    const tierPriority: Record<string, number> = {
      gold: 5,
      silver: 4,
      bronze: 3,
      single: 2,
      sandbox: 1,
    };

    return matched.reduce((best, current) => {
      const bestScore = tierPriority[best.tier] || 0;
      const currentScore = tierPriority[current.tier] || 0;
      return currentScore > bestScore ? current : best;
    }, matched[0]);
  })();

  // 설정이 아직 로드되지 않았으면 전환 동작을 일절 노출하지 않는다. 로드 전에 저장을 보내면
  // trade_mode 폴백값이 실제 계정 모드(REAL/MOCK)를 덮어써 조용히 강등시킬 수 있다.
  const isSettingsReady = Boolean(adminSettings);
  const currentActiveStrategyId = adminSettings?.strategy_type || DEFAULT_STRATEGY_ID;

  const currentStrategy = strategies?.find((s) => s.id === currentActiveStrategyId);
  const currentStrategyName = currentStrategy?.name || currentActiveStrategyId;
  const currentStrategyTier = currentStrategy?.tier || "single";

  const targetRecommended = recommendedStrategy || currentStrategy;
  const isAlreadyApplied = !targetRecommended || currentActiveStrategyId === targetRecommended.id;
  // 추천·최적 여부는 국면이 확정된 뒤에만 주장할 수 있다.
  const canJudgeOptimality = isRegimeReady && Boolean(targetRecommended);

  // 실제 저장. 확인 단계를 거친 뒤에만 호출된다.
  const applyStrategy = async (strategyId: string) => {
    if (isApplying || !adminSettings) return;

    setIsApplying(true);
    try {
      await adminAPI.saveSettings({
        // 폴백 없이 로드된 실제 설정값만 되돌려 보낸다(부분 저장으로 다른 필드가 뒤집히지 않게).
        trade_mode: adminSettings.trade_mode,
        broker_provider: adminSettings.broker_provider ?? null,
        telegram_chat_id: adminSettings.telegram_chat_id ?? null,
        telegram_enabled: adminSettings.telegram_enabled ?? false,
        strategy_type: strategyId,
      });

      await mutateSettings();
      const targetStrat = strategies?.find((s) => s.id === strategyId);
      toast.success(t("market_regime.change_success", { name: targetStrat?.name || strategyId }));
    } catch (err: unknown) {
      console.error(err);
      const axiosErr = err as { response?: { data?: { detail?: string; error?: { message?: string } } }; message?: string };
      const detailMsg =
        axiosErr?.response?.data?.detail ||
        axiosErr?.response?.data?.error?.message ||
        axiosErr?.message ||
        t("market_regime.change_failed");
      toast.error(detailMsg);
    } finally {
      setIsApplying(false);
    }
  };

  // 대시보드에서의 전환은 라이브 자동매매 전략을 즉시 교체하므로, 설정 화면의 '저장 버튼'에
  // 대응하는 명시적 2단계 확인을 거친다(한 번의 클릭으로 라이브가 바뀌지 않는다).
  const handleSelectStrategy = (strategyId: string) => {
    if (isApplying || !adminSettings) return;

    const targetStrat = strategies?.find((s) => s.id === strategyId);
    toast(t("market_regime.confirm_title", { name: targetStrat?.name || strategyId }), {
      description: t("market_regime.confirm_desc", { mode: adminSettings.trade_mode }),
      action: {
        label: t("market_regime.confirm_action"),
        onClick: () => {
          void applyStrategy(strategyId);
        },
      },
      cancel: {
        label: t("market_regime.confirm_cancel"),
        onClick: () => {},
      },
    });
  };

  const getRegimeBadge = (regime: string) => {
    switch (regime) {
      case "BULLISH":
        return {
          label: t("market_regime.regime_bullish"),
          icon: <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />,
          color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
          dot: "bg-emerald-400",
        };
      case "BEARISH":
        return {
          label: t("market_regime.regime_bearish"),
          icon: <Shield className="w-3.5 h-3.5 text-blue-400" />,
          color: "bg-blue-500/10 text-blue-400 border-blue-500/30",
          dot: "bg-blue-400",
        };
      default:
        return {
          label: t("market_regime.regime_neutral"),
          icon: <Target className="w-3.5 h-3.5 text-purple-400" />,
          color: "bg-purple-500/10 text-purple-400 border-purple-500/30",
          dot: "bg-purple-400",
        };
    }
  };

  const regimeInfo = currentRegime ? getRegimeBadge(currentRegime) : null;

  return (
    <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-indigo-950/40 via-zinc-900/80 to-purple-950/40 border border-indigo-500/25 p-4 md:p-5 shadow-xl transition-all duration-300">
      <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-full blur-3xl pointer-events-none" />

      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10">
        {/* 통합 정보 (국면 진단 + 현재 실행 중인 전략 + 설명) */}
        <div className="space-y-1.5 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-black uppercase tracking-wider bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
              <Sparkles className="w-3 h-3 text-amber-400 animate-pulse" />
              {t("market_regime.badge_title")}
            </span>

            {regimeInfo ? (
              <span className={`flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold border ${regimeInfo.color}`}>
                <span className={`w-1.5 h-1.5 rounded-full ${regimeInfo.dot} animate-ping`} />
                {regimeInfo.icon}
                {regimeInfo.label}
              </span>
            ) : (
              <span className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-extrabold border bg-zinc-500/10 text-zinc-400 border-zinc-500/30">
                <Loader2 className="w-3 h-3 animate-spin" />
                {t("market_regime.regime_unknown")}
              </span>
            )}
          </div>

          <div className="pt-1 flex flex-col sm:flex-row sm:items-center gap-2">
            <span className="text-xs text-zinc-400 font-medium">{t("market_regime.current_label")}</span>
            <span className="text-sm font-extrabold text-white flex items-center gap-1.5">
              🥇 {currentStrategyName}
              <span className="text-[10px] text-indigo-400 font-mono px-1.5 py-0.2 bg-indigo-500/10 border border-indigo-500/20 rounded uppercase">
                {t("market_regime.tier_suffix", { tier: currentStrategyTier })}
              </span>
            </span>

            {!canJudgeOptimality ? null : isAlreadyApplied ? (
              <span className="text-[11px] text-emerald-400 font-bold flex items-center gap-1 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                <CheckCircle2 className="w-3.5 h-3.5" /> {t("market_regime.optimal_running")}
              </span>
            ) : (
              <span className="text-[11px] text-amber-400 font-bold flex items-center gap-1 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                {t("market_regime.recommend", { name: targetRecommended.name })}
              </span>
            )}
          </div>

          <p className="text-xs text-zinc-300 leading-relaxed max-w-3xl line-clamp-1">
            {currentStrategy?.summary_ko || t("market_regime.default_summary")}
          </p>
        </div>

        {/* 액션 버튼 그룹 (1-Click 적용 및 전략 변경 모달 팝업) */}
        <div className="shrink-0 flex items-center gap-2.5">
          {!isSettingsReady && (
            <span className="flex items-center gap-1.5 text-[11px] text-zinc-400 font-semibold">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
              {t("market_regime.loading")}
            </span>
          )}

          {isSettingsReady && canJudgeOptimality && !isAlreadyApplied && targetRecommended && (
            <button
              type="button"
              disabled={isApplying}
              onClick={() => handleSelectStrategy(targetRecommended.id)}
              className="inline-flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-xl text-xs font-bold transition-all bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white shadow-md shadow-indigo-600/20 active:scale-95 cursor-pointer"
            >
              {isApplying ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-white" />
              ) : (
                <Zap className="w-3.5 h-3.5 text-amber-300 fill-amber-300" />
              )}
              <span>{t("market_regime.apply_recommended")}</span>
            </button>
          )}

          <button
            type="button"
            disabled={!isSettingsReady}
            onClick={() => setIsModalOpen(true)}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2.5 rounded-xl text-xs font-bold transition-all bg-zinc-800/90 hover:bg-zinc-700 text-zinc-200 hover:text-white border border-zinc-700/80 active:scale-95 cursor-pointer shadow-sm"
          >
            <Award className="w-3.5 h-3.5 text-indigo-400" />
            <span>{t("market_regime.change_and_compare")}</span>
          </button>
        </div>
      </div>

      {/* 전략 선택 및 성과 비교 팝업 모달 */}
      <StrategySelectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        selectedStrategyId={currentActiveStrategyId}
        onSelectStrategy={handleSelectStrategy}
      />
    </div>
  );
}
