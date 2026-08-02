"use client";

import React from "react";
import Link from "next/link";
import { Loader2, Settings, ArrowRight } from "lucide-react";
import { useTranslations } from "next-intl";
import { useCurrentStrategy } from "@/hooks/useStrategyCatalog";

// 대시보드에서 "지금 무엇이 돌고 있는지"만 읽기 전용으로 보여주는 배지.
// 전략 변경(SSOT)은 /admin/settings 로만 이동한다. 즉시 라이브 전환은 여기서 하지 않는다.
export function CurrentStrategyBadge() {
  const t = useTranslations("dashboard");
  const { currentId, current, isLoading } = useCurrentStrategy();

  const tierBadge = (tier?: string) => {
    switch (tier) {
      case 'gold': return { badge: 'bg-amber-500/10 text-amber-400 border-amber-500/20', label: '🥇 GOLD' };
      case 'silver': return { badge: 'bg-slate-400/10 text-slate-300 border-slate-400/20', label: '🥈 SILVER' };
      case 'bronze': return { badge: 'bg-orange-500/10 text-orange-400 border-orange-500/20', label: '🥉 BRONZE' };
      case 'sandbox': return { badge: 'bg-fuchsia-500/10 text-fuchsia-400 border-fuchsia-500/20', label: '🧪 SANDBOX' };
      default: return { badge: 'bg-blue-500/10 text-blue-400 border-blue-500/20', label: '💠 MODULE' };
    }
  };
  const tier = tierBadge(current?.tier);

  return (
    <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={`px-2 py-0.5 rounded text-[10px] font-black tracking-wider border ${tier.badge}`}>
              {tier.label}
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-400/80">
              {t("current_strategy_running")}
            </span>
          </div>

          {isLoading ? (
            <div className="flex items-center gap-2 text-zinc-500 text-sm">
              <Loader2 className="w-4 h-4 animate-spin" />
            </div>
          ) : (
            <>
              <h3 className="text-lg font-extrabold text-slate-100 truncate">
                {current?.name || currentId}
              </h3>
              <p className="text-xs text-zinc-400 mt-1 line-clamp-2 max-w-2xl leading-relaxed">
                {current?.summary_ko || current?.description || t("current_strategy_unset")}
              </p>
              <p className="text-[11px] text-zinc-600 mt-2">
                {t("current_strategy_regime_hint")}
              </p>
            </>
          )}
        </div>

        <Link
          href="/admin/settings"
          className="shrink-0 inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-zinc-700 bg-zinc-800/60 hover:bg-zinc-700 text-zinc-200 text-xs font-bold transition-colors"
        >
          <Settings className="w-3.5 h-3.5" />
          {t("current_strategy_change")}
          <ArrowRight className="w-3.5 h-3.5" />
        </Link>
      </div>
    </div>
  );
}
