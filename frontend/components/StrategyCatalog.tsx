"use client";

import React, { useState } from "react";
import { Loader2, Award, ChevronDown, Sparkles } from "lucide-react";
import { useTranslations } from "next-intl";
import { useStrategyCatalog } from "@/hooks/useStrategyCatalog";
import { StrategySelectModal } from "./StrategySelectModal";

interface StrategyCatalogProps {
  // 현재 선택된 전략 id (제어 컴포넌트)
  value?: string;
  // 선택 시 부모 폼 상태만 갱신
  onSelect: (strategyId: string) => void;
}

export function StrategyCatalog({ value, onSelect }: StrategyCatalogProps) {
  const t = useTranslations("components");
  const { strategies, error: strategiesError } = useStrategyCatalog();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const currentStrategyId = value || "regime_switching";

  if (strategiesError) {
    return (
      <div className="p-3 bg-red-950/20 text-red-400 text-xs rounded-xl border border-red-900/30">
        {t("strategy_catalog.settings_load_failed")}
      </div>
    );
  }

  if (!strategies) {
    return (
      <div className="flex items-center justify-center p-3 bg-zinc-900/20 rounded-xl border border-zinc-800">
        <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
      </div>
    );
  }

  return (
    <div className="w-full">
      {/* 1줄 미니멀 스마트 컨트롤 바 */}
      <div className="flex flex-col sm:flex-row gap-2.5 items-stretch sm:items-center w-full">
        {/* 셀렉트 드롭다운 */}
        <div className="relative flex-1 min-w-0">
          <select
            value={currentStrategyId}
            onChange={(e) => onSelect(e.target.value)}
            className="w-full appearance-none bg-zinc-900 border border-zinc-800 hover:border-zinc-700 rounded-xl px-4 py-2.5 text-xs font-bold text-white focus:outline-none focus:border-indigo-500 transition-colors pr-10 cursor-pointer shadow-inner truncate"
          >
            {strategies.map((strategy) => (
              <option key={strategy.id} value={strategy.id} className="bg-zinc-900 text-zinc-100 py-2">
                {strategy.name} ({strategy.id}) — [{strategy.tier.toUpperCase()}]
              </option>
            ))}
          </select>
          <ChevronDown className="w-4 h-4 text-zinc-400 absolute right-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>

        {/* 전략 카탈로그 & 상세 비교 팝업 버튼 */}
        <button
          type="button"
          onClick={() => setIsModalOpen(true)}
          className="flex items-center justify-center gap-2 px-4 py-2.5 bg-indigo-600/15 hover:bg-indigo-600/25 border border-indigo-500/30 hover:border-indigo-500/50 text-indigo-300 hover:text-white rounded-xl text-xs font-bold transition-all active:scale-[0.98] shrink-0 shadow-sm whitespace-nowrap"
        >
          <Award className="w-4 h-4 text-indigo-400" />
          <span>{t("strategy_catalog.catalog_and_compare")}</span>
          <Sparkles className="w-3.5 h-3.5 text-amber-400" />
        </button>
      </div>

      {/* 팝업 모달 */}
      <StrategySelectModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        selectedStrategyId={currentStrategyId}
        onSelectStrategy={onSelect}
      />
    </div>
  );
}
