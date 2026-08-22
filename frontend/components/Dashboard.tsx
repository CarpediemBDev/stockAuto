"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { TradeLogs } from "./TradeLogs";
import { AccountBalance } from "./AccountBalance";
import PortfolioView from "./PortfolioView";
import { AssetTrendChart } from "./AssetTrendChart";
import { LiveTradeTicker } from "./LiveTradeTicker";
import { AIMarketRegimeWidget } from "./AIMarketRegimeWidget";
import { Modal, SegmentedControl } from "@/components/ui";

import useSWR from "swr";
import { pollInterval } from "@/lib/sse";
import { fetcher } from "@/lib/api";

export function Dashboard() {
  const { data: statusData } = useSWR('/bot/status', fetcher, { refreshInterval: pollInterval(15000) });
  const { data: logsData } = useSWR('/trades', fetcher, { refreshInterval: pollInterval(15000) });

  const isBotRunning = statusData?.is_running || false;
  const isReal = statusData?.is_real || false;
  const logs = logsData || [];

  const [isChartOpen, setIsChartOpen] = useState(false);
  const [isLogsModalOpen, setIsLogsModalOpen] = useState(false);

  const [displayCurrency, setDisplayCurrency] = useState<"KRW" | "USD">("KRW");
  const t = useTranslations("dashboard");

  return (
    <div className={`min-h-screen transition-colors duration-700 ${isReal && isBotRunning ? 'bg-red-950/20' : 'bg-background'}`}>
      <div className="max-w-[1600px] mx-auto p-6 pt-6 space-y-6">
        <LiveTradeTicker latestLog={logs[0]} onClick={() => setIsLogsModalOpen(true)} />

        <AIMarketRegimeWidget />

        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-extrabold text-white tracking-tight flex items-center gap-3">
            <span className="bg-indigo-600 w-2.5 h-6 rounded-full"></span>
            {t("account_status")}
          </h1>
          
          <div className="flex items-center gap-3">
            <SegmentedControl<"USD" | "KRW">
              value={displayCurrency}
              onChange={setDisplayCurrency}
              size="sm"
              options={[
                { value: "USD", label: t("currency_usd") },
                { value: "KRW", label: t("currency_krw") },
              ]}
            />
          </div>
        </div>

        <AccountBalance displayCurrency={displayCurrency} onTotalAssetClick={() => setIsChartOpen(true)} />
        
        <div className="mb-6">
          <h2 className="text-xl font-bold text-slate-100 mb-4 flex items-center">
            <div className="w-1.5 h-6 bg-indigo-500 rounded-full mr-3"></div>
            {t("portfolio_title")}
          </h2>
          <PortfolioView displayCurrency={displayCurrency} />
        </div>
      </div>

      {/* 자산 성장 차트 모달 */}
      <Modal
        isOpen={isChartOpen}
        onClose={() => setIsChartOpen(false)}
        maxWidth="4xl"
      >
        <AssetTrendChart displayCurrency={displayCurrency} logs={logs} />
      </Modal>

      {/* 전체 거래 내역 상세 조회 모달 */}
      <Modal
        isOpen={isLogsModalOpen}
        onClose={() => setIsLogsModalOpen(false)}
        maxWidth="5xl"
      >
        <TradeLogs logs={logs} isModalMode={true} />
      </Modal>
    </div>
  );
}
