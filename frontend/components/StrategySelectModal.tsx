"use client";

import React from "react";
import { Loader2, CheckCircle2, Shield, Zap, TrendingUp, Target, X, Award } from "lucide-react";
import { useTranslations } from "next-intl";
import { useStrategyCatalog } from "@/hooks/useStrategyCatalog";

interface StrategySelectModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedStrategyId: string;
  onSelectStrategy: (strategyId: string) => void;
}

export function StrategySelectModal({
  isOpen,
  onClose,
  selectedStrategyId,
  onSelectStrategy,
}: StrategySelectModalProps) {
  const t = useTranslations("components");
  const { strategies, error: strategiesError } = useStrategyCatalog();

  if (!isOpen) return null;

  const getTierConfig = (tier: string) => {
    switch (tier) {
      case "gold":
        return {
          color: "from-amber-400 to-yellow-600",
          badge: "bg-amber-500/10 text-amber-400 border-amber-500/30",
          label: "🥇 GOLD TIER",
        };
      case "silver":
        return {
          color: "from-slate-300 to-zinc-500",
          badge: "bg-slate-400/10 text-slate-300 border-slate-400/30",
          label: "🥈 SILVER TIER",
        };
      case "bronze":
        return {
          color: "from-orange-400 to-amber-700",
          badge: "bg-orange-500/10 text-orange-400 border-orange-500/30",
          label: "🥉 BRONZE TIER",
        };
      case "sandbox":
        return {
          color: "from-fuchsia-400 to-purple-600",
          badge: "bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/30",
          label: "🧪 SANDBOX",
        };
      default:
        return {
          color: "from-blue-400 to-indigo-600",
          badge: "bg-blue-500/10 text-blue-400 border-blue-500/30",
          label: "💠 SINGLE MODULE",
        };
    }
  };

  const getRegimeIcon = (regime: string) => {
    switch (regime) {
      case "ALL":
        return <Globe className="w-4 h-4 text-emerald-400" />;
      case "BULLISH":
        return <TrendingUp className="w-4 h-4 text-rose-500" />;
      case "BEARISH":
        return <Shield className="w-4 h-4 text-blue-400" />;
      case "NEUTRAL":
        return <Target className="w-4 h-4 text-purple-400" />;
      default:
        return <Zap className="w-4 h-4 text-zinc-400" />;
    }
  };

  const getRegimeLabel = (regime: string) => {
    switch (regime) {
      case "ALL":
        return t("strategy_catalog.regime_all");
      case "BULLISH":
        return t("strategy_catalog.regime_bullish");
      case "BEARISH":
        return t("strategy_catalog.regime_bearish");
      case "NEUTRAL":
        return t("strategy_catalog.regime_neutral");
      default:
        return regime;
    }
  };

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-0 bg-black/80 backdrop-blur-md z-50 flex items-center justify-center p-4 animate-in fade-in duration-200"
    >
      <div className="bg-zinc-950 border border-zinc-800 rounded-3xl max-w-5xl w-full p-6 relative shadow-2xl animate-in zoom-in-95 duration-200 flex flex-col max-h-[90vh]">
        {/* 헤더 영역 */}
        <div className="flex justify-between items-start pb-4 mb-4 border-b border-zinc-800 shrink-0">
          <div>
            <h2 className="text-xl font-extrabold text-white flex items-center gap-2.5">
              <Award className="w-5 h-5 text-indigo-400" />
              {t("strategy_catalog.modal_title")}
            </h2>
            <p className="text-xs text-zinc-400 mt-1">
              {t("strategy_catalog.modal_subtitle")}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-white p-2 rounded-full hover:bg-zinc-900 active:scale-95 transition-all font-bold"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 컨텐츠 영역 */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-4">
          {strategiesError && (
            <div className="p-4 bg-red-950/20 text-red-400 rounded-xl border border-red-900/30">
              {t("strategy_catalog.settings_load_failed")}
            </div>
          )}

          {!strategies ? (
            <div className="flex items-center justify-center p-16 bg-zinc-900/20 rounded-2xl border border-zinc-800">
              <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
              {strategies.map((strategy) => {
                const isSelected = selectedStrategyId === strategy.id;
                const tierConfig = getTierConfig(strategy.tier);

                return (
                  <div
                    key={strategy.id}
                    onClick={() => {
                      onSelectStrategy(strategy.id);
                      onClose();
                    }}
                    className={`
                      relative flex flex-col p-5 rounded-2xl cursor-pointer transition-all duration-300 overflow-hidden
                      ${
                        isSelected
                          ? "bg-zinc-900 border-2 border-indigo-500 shadow-[0_0_25px_rgba(99,102,241,0.2)] transform scale-[1.02]"
                          : "bg-zinc-900/50 border border-zinc-800 hover:bg-zinc-800/80 hover:border-zinc-700"
                      }
                    `}
                  >
                    {isSelected && (
                      <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 to-cyan-400" />
                    )}

                    <div className="flex justify-between items-center mb-3">
                      <div className={`px-2.5 py-0.5 rounded text-[11px] font-black tracking-wider border ${tierConfig.badge}`}>
                        {tierConfig.label}
                      </div>
                      {isSelected && (
                        <span className="flex items-center gap-1 text-xs font-bold text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded-full border border-indigo-500/20">
                          <CheckCircle2 className="w-3.5 h-3.5" /> {t("strategy_catalog.selected")}
                        </span>
                      )}
                    </div>

                    <h3 className="text-base font-extrabold text-slate-100 mb-0.5">{strategy.name}</h3>
                    <p className="text-[11px] text-zinc-500 font-mono mb-3">{strategy.id}</p>

                    <div className="flex-grow mb-4">
                      <p className="text-xs text-zinc-300 leading-relaxed line-clamp-4">
                        {strategy.summary_ko || strategy.description || t("strategy_catalog.no_description")}
                      </p>
                    </div>

                    <div className="pt-3 border-t border-zinc-800/60 flex items-center justify-between mt-auto">
                      <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-black/40 border border-zinc-800/50">
                        {getRegimeIcon(strategy.regime)}
                        <span className="text-[11px] font-semibold text-zinc-400">{getRegimeLabel(strategy.regime)}</span>
                      </div>

                      <button
                        type="button"
                        className={`text-xs font-bold px-3 py-1.5 rounded-lg transition-all ${
                          isSelected
                            ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30"
                            : "bg-zinc-800 text-zinc-300 hover:bg-indigo-600 hover:text-white"
                        }`}
                      >
                        {isSelected ? t("strategy_catalog.applying") : t("strategy_catalog.select_action")}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
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
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10z" />
      <path d="M2 12h20" />
    </svg>
  );
}
