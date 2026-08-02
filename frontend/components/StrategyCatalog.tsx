"use client";

import React from "react";
import { Loader2, CheckCircle2, Shield, Zap, TrendingUp, Target } from "lucide-react";
import { useTranslations } from "next-intl";
import { useStrategyCatalog } from "@/hooks/useStrategyCatalog";

interface StrategyCatalogProps {
  // 현재 선택된 전략 id (제어 컴포넌트). 부모(설정 화면)의 폼 상태가 SSOT다.
  value?: string;
  // 카드 클릭 시 부모 폼 상태만 갱신한다. 실제 저장은 부모의 저장 버튼이 담당(즉시 라이브 전환 금지).
  onSelect: (strategyId: string) => void;
}

export function StrategyCatalog({ value, onSelect }: StrategyCatalogProps) {
  const t = useTranslations("components");
  const { strategies, error: strategiesError } = useStrategyCatalog();

  const currentStrategy = value || "regime_switching";

  if (strategiesError) {
    return <div className="p-4 bg-red-950/20 text-red-400 rounded-xl border border-red-900/30">{t("strategy_catalog.settings_load_failed")}</div>;
  }

  if (!strategies) {
    return (
      <div className="flex items-center justify-center p-12 bg-zinc-900/20 rounded-2xl border border-zinc-800">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
      </div>
    );
  }

  const getTierConfig = (tier: string) => {
    switch(tier) {
      case 'gold': return { color: 'from-amber-400 to-yellow-600', badge: 'bg-amber-500/10 text-amber-400 border-amber-500/20', label: '🥇 GOLD TIER' };
      case 'silver': return { color: 'from-slate-300 to-zinc-500', badge: 'bg-slate-400/10 text-slate-300 border-slate-400/20', label: '🥈 SILVER TIER' };
      case 'bronze': return { color: 'from-orange-400 to-amber-700', badge: 'bg-orange-500/10 text-orange-400 border-orange-500/20', label: '🥉 BRONZE TIER' };
      case 'sandbox': return { color: 'from-fuchsia-400 to-purple-600', badge: 'bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20', label: '🧪 SANDBOX' };
      default: return { color: 'from-blue-400 to-indigo-600', badge: 'bg-blue-500/10 text-blue-400 border-blue-500/20', label: '💠 SINGLE MODULE' };
    }
  };

  const getRegimeIcon = (regime: string) => {
    switch(regime) {
      case 'ALL': return <Globe className="w-4 h-4 text-emerald-400" />;
      case 'BULLISH': return <TrendingUp className="w-4 h-4 text-rose-500" />;
      case 'BEARISH': return <Shield className="w-4 h-4 text-blue-400" />;
      case 'NEUTRAL': return <Target className="w-4 h-4 text-purple-400" />;
      default: return <Zap className="w-4 h-4 text-zinc-400" />;
    }
  };

  const getRegimeLabel = (regime: string) => {
    switch(regime) {
      case 'ALL': return t("strategy_catalog.regime_all");
      case 'BULLISH': return t("strategy_catalog.regime_bullish");
      case 'BEARISH': return t("strategy_catalog.regime_bearish");
      case 'NEUTRAL': return t("strategy_catalog.regime_neutral");
      default: return regime;
    }
  };

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {strategies.map((strategy) => {
          const isSelected = currentStrategy === strategy.id;
          const tierConfig = getTierConfig(strategy.tier);

          return (
            <div
              key={strategy.id}
              onClick={() => onSelect(strategy.id)}
              className={`
                relative flex flex-col p-5 rounded-2xl cursor-pointer transition-all duration-300 overflow-hidden
                ${isSelected
                  ? 'bg-zinc-900 border-2 border-indigo-500 shadow-[0_0_20px_rgba(99,102,241,0.15)] transform scale-[1.02]'
                  : 'bg-zinc-900/40 border border-zinc-800 hover:bg-zinc-800/60 hover:border-zinc-700'
                }
              `}
            >
              {isSelected && (
                <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 to-cyan-400" />
              )}

              <div className="flex justify-between items-start mb-3">
                <div className={`px-2 py-0.5 rounded text-[10px] font-black tracking-wider border ${tierConfig.badge}`}>
                  {tierConfig.label}
                </div>
                {isSelected && (
                  <CheckCircle2 className="w-5 h-5 text-indigo-400 drop-shadow-md" />
                )}
              </div>

              <h3 className="text-lg font-extrabold text-slate-100 mb-1">{strategy.name}</h3>
              <p className="text-xs text-zinc-500 font-mono mb-4">{strategy.id}</p>

              <div className="flex-grow">
                <p className="text-sm text-zinc-300 leading-relaxed line-clamp-3">
                  {strategy.summary_ko || strategy.description || t("strategy_catalog.no_description")}
                </p>
              </div>

              <div className="mt-5 pt-4 border-t border-zinc-800/50 flex items-center justify-between">
                <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-black/40 border border-zinc-800/50">
                  {getRegimeIcon(strategy.regime)}
                  <span className="text-xs font-semibold text-zinc-400">{getRegimeLabel(strategy.regime)}</span>
                </div>

                <button
                  type="button"
                  className={`text-xs font-bold px-3 py-1 rounded-full transition-colors ${
                    isSelected
                      ? 'bg-indigo-500/20 text-indigo-300 cursor-default'
                      : 'bg-zinc-800 text-zinc-300 hover:bg-zinc-700'
                  }`}
                >
                  {isSelected ? t("strategy_catalog.selected") : t("strategy_catalog.select")}
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Globe(props: React.SVGProps<SVGSVGElement>) {
  return (
    <svg
      {...props}
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="10" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      <path d="M2 12h20" />
    </svg>
  )
}
