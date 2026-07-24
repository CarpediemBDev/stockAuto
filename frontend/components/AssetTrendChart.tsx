"use client";

import { useMemo, useState, useEffect, useRef } from "react";
import { TradeLog } from "./TradeLogs";
import { accountAPI, isCancel } from "@/lib/api";
import { reportHandledError, DEFAULT_FX_RATE, krwToUsd, usdToKrw } from "@/lib/utils";
import { useTranslations } from "next-intl";

interface AssetTrendChartProps {
  displayCurrency: "KRW" | "USD";
  logs: TradeLog[];
}

export function AssetTrendChart({ displayCurrency, logs }: AssetTrendChartProps) {
  const t = useTranslations("components");
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [realTotalAsset, setRealTotalAsset] = useState<number | null>(null);
  const [fxRate, setFxRate] = useState<number>(DEFAULT_FX_RATE);
  const [historyData, setHistoryData] = useState<{ timestamp: string; total: number }[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  // 1. 실시간 실제 계좌 및 역사적 스냅샷 정보를 API로부터 조회
  useEffect(() => {
    let active = true;
    const fetchRealAsset = async () => {
      try {
        const res = await accountAPI.getBalance();
        const historyRes = await accountAPI.getHistory();
        if (active) {
          setRealTotalAsset(res.data.total_asset);
          if (res.data.fx_rate && res.data.fx_rate > 0) {
            setFxRate(res.data.fx_rate);
          }
          if (Array.isArray(historyRes.data)) {
            setHistoryData(historyRes.data);
          }
          setIsLoading(false);
        }
      } catch (err) {
        if (isCancel(err)) return;
        reportHandledError("[AssetTrendChart] Failed to fetch real asset", err);
        if (active) {
          setIsLoading(false);
        }
      }
    };

    fetchRealAsset();
    return () => {
      active = false;
    };
  }, []);

  // 2. 실제 자산 연산 알고리즘 (방향 A - 100% 정밀 실제 데이터 연동)
  const chartData = useMemo(() => {
    if (realTotalAsset === null) return [];

    // 최신 환율 기준 실시간 총 자산 (달러 환산 기준점으로 통일 후 프론트에서 가변 포맷팅)
    const currentAssetUsd = krwToUsd(realTotalAsset, fxRate);

    // 만약 실제 스냅샷 이력이 전혀 없는 신규 계좌일 경우:
    // 현재 실제 자산 가치 그대로 수평선을 그려 "거래 변동 없는 투명한 잔고"를 표현
    if (!historyData || historyData.length === 0) {
      const today = new Date();
      return Array.from({ length: 7 }).map((_, i) => {
        const d = new Date(today);
        d.setDate(today.getDate() - (6 - i));
        const dateStr = `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        return {
          date: dateStr,
          usd: Math.round(currentAssetUsd),
          isRealTx: false,
        };
      });
    }

    // 스냅샷 데이터(total_asset은 KRW 단위로 백엔드에서 반환됨)를 USD로 가공하여 매핑
    const historyPoints = historyData.map((s) => {
      const logDate = new Date(s.timestamp);
      const dateStr = `${String(logDate.getMonth() + 1).padStart(2, "0")}-${String(logDate.getDate()).padStart(2, "0")}`;
      return {
        date: dateStr,
        usd: Math.round(krwToUsd(s.total, fxRate)),
        isRealTx: true,
      };
    });

    // 포인트가 너무 적으면 앞쪽에 시작점 기반 수평 보조 포인트를 덧붙여 7개 이상의 흐름을 만들어냅니다.
    if (historyPoints.length < 7) {
      const needed = 7 - historyPoints.length;
      const firstTxDate = new Date(historyData[0].timestamp);
      const startUsd = Math.round(krwToUsd(historyData[0].total, fxRate));

      const fillPoints = Array.from({ length: needed }).map((_, i) => {
        const d = new Date(firstTxDate);
        d.setDate(firstTxDate.getDate() - (needed - i));
        const dateStr = `${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
        return {
          date: dateStr,
          usd: startUsd,
          isRealTx: false,
        };
      });
      return [...fillPoints, ...historyPoints];
    }

    return historyPoints.slice(-12); // 최근 최대 12개 변화량 렌더링
  }, [historyData, realTotalAsset, fxRate]);

  // 3. SVG 차트 좌표 계산
  const width = 800;
  const height = 240;
  const padding = 24;

  const minVal = useMemo(() => {
    if (chartData.length === 0) return 0;
    const min = Math.min(...chartData.map((d) => d.usd));
    return min * 0.99;
  }, [chartData]);

  const maxVal = useMemo(() => {
    if (chartData.length === 0) return 100;
    const max = Math.max(...chartData.map((d) => d.usd));
    return max * 1.01;
  }, [chartData]);

  const points = useMemo(() => {
    if (chartData.length === 0) return [];
    return chartData.map((d, i) => {
      const x = padding + (i / (chartData.length - 1)) * (width - padding * 2);
      // 만약 최댓값과 최솟값이 같은 완벽한 수평선(무거래 상태)인 경우, 차트 정중앙에 수평선 렌더링
      const range = maxVal - minVal;
      const y = range === 0
        ? height / 2
        : height - padding - ((d.usd - minVal) / range) * (height - padding * 2);
      return { x, y, ...d };
    });
  }, [chartData, minVal, maxVal]);

  const linePath = useMemo(() => {
    if (points.length === 0) return "";
    return points.reduce((path, p, i) => {
      return i === 0 ? `M ${p.x} ${p.y}` : `${path} L ${p.x} ${p.y}`;
    }, "");
  }, [points]);

  const areaPath = useMemo(() => {
    if (points.length === 0) return "";
    const first = points[0];
    const last = points[points.length - 1];
    return `${linePath} L ${last.x} ${height - padding} L ${first.x} ${height - padding} Z`;
  }, [points, linePath]);

  // 4. 포맷팅 헬퍼
  const formatCurrency = (usdVal: number) => {
    if (displayCurrency === "USD") {
      return `$${usdVal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    } else {
      const krwVal = Math.round(usdToKrw(usdVal, fxRate));
      return `${krwVal.toLocaleString()}${t("common.krw_suffix")}`;
    }
  };

  // 5. 호버 핸들러
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement, MouseEvent>) => {
    if (!containerRef.current || points.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const svgMouseX = (mouseX / rect.width) * width;

    let closestIndex = 0;
    let minDiff = Infinity;
    points.forEach((p, i) => {
      const diff = Math.abs(p.x - svgMouseX);
      if (diff < minDiff) {
        minDiff = diff;
        closestIndex = i;
      }
    });

    setHoveredIndex(closestIndex);

    const hoveredPoint = points[closestIndex];
    const tooltipX = (hoveredPoint.x / width) * rect.width;
    const tooltipY = (hoveredPoint.y / height) * rect.height - 45;
    setTooltipPos({ x: tooltipX, y: tooltipY });
  };

  const handleMouseLeave = () => {
    setHoveredIndex(null);
  };

  // 변화량 계산
  const firstVal = chartData[0]?.usd || 0;
  const lastVal = chartData[chartData.length - 1]?.usd || 0;
  const changePct = firstVal > 0 ? ((lastVal - firstVal) / firstVal) * 100 : 0;

  // 로딩 스켈레톤 UI
  if (isLoading || realTotalAsset === null) {
    return (
      <div className="w-full h-[320px] bg-zinc-950/70 border border-zinc-900 rounded-2xl p-6 flex flex-col justify-between animate-pulse">
        <div className="space-y-2">
          <div className="h-3 bg-zinc-900 rounded w-1/4"></div>
          <div className="h-8 bg-zinc-900 rounded w-1/3"></div>
        </div>
        <div className="w-full h-[180px] bg-zinc-900/50 rounded-xl flex items-center justify-center">
          <span className="text-xs text-zinc-600 font-bold">{t("asset_chart.loading")}</span>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full bg-zinc-950/40 border border-zinc-900 rounded-2xl p-6 backdrop-blur-md overflow-hidden shadow-2xl transition-all duration-300"
    >
      {/* Glow Effect */}
      <div className="absolute -top-24 -left-24 w-80 h-80 bg-indigo-500/5 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute -bottom-24 -right-24 w-80 h-80 bg-blue-500/5 rounded-full blur-[100px] pointer-events-none" />

      {/* 헤더 */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <span className="text-[10px] text-zinc-500 font-black tracking-widest uppercase flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
            {t("asset_chart.title")}
          </span>
          <div className="flex items-baseline gap-3 mt-1">
            <h3 className="text-2xl font-black text-white tracking-tight">
              {hoveredIndex !== null
                ? formatCurrency(chartData[hoveredIndex].usd)
                : formatCurrency(lastVal)}
            </h3>
            {changePct !== 0 && (
              <span
                className={`text-xs font-extrabold px-2 py-0.5 rounded-full ${
                  changePct >= 0 ? "bg-emerald-950/50 text-emerald-400" : "bg-red-950/50 text-red-400"
                }`}
              >
                {changePct >= 0 ? "+" : ""}
                {changePct.toFixed(2)}%
              </span>
            )}
          </div>
          <p className="text-[10px] text-zinc-600 mt-1">
            {hoveredIndex !== null
              ? t("asset_chart.hover_date", { date: chartData[hoveredIndex].date })
              : logs && logs.length > 0
              ? t("asset_chart.has_history")
              : t("asset_chart.no_history")}
          </p>
        </div>
      </div>

      {/* SVG 차트 영역 */}
      <div className="relative w-full h-[200px]">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-full cursor-crosshair overflow-visible"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            <linearGradient id="chart-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgb(99, 102, 241)" stopOpacity="0.25" />
              <stop offset="60%" stopColor="rgb(59, 130, 246)" stopOpacity="0.08" />
              <stop offset="100%" stopColor="rgb(9, 9, 11)" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id="line-gradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="rgb(59, 130, 246)" />
              <stop offset="50%" stopColor="rgb(99, 102, 241)" />
              <stop offset="100%" stopColor="rgb(168, 85, 247)" />
            </linearGradient>
          </defs>

          {/* 수평 보조선 */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
            const y = padding + ratio * (height - padding * 2);
            return (
              <line
                key={i}
                x1={padding}
                y1={y}
                x2={width - padding}
                y2={y}
                stroke="rgba(63, 63, 70, 0.12)"
                strokeWidth="1"
                strokeDasharray="4 4"
              />
            );
          })}

          {/* Area 채우기 */}
          {areaPath && (
            <path
              d={areaPath}
              fill="url(#chart-gradient)"
              className="transition-all duration-300"
            />
          )}

          {/* 메인 꺾은선 */}
          {linePath && (
            <path
              d={linePath}
              fill="none"
              stroke="url(#line-gradient)"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="transition-all duration-300"
            />
          )}

          {/* X축 라벨 */}
          {points.map((p, i) => {
            const isLabelVisible = i === 0 || i === points.length - 1 || i === Math.floor(points.length / 2);
            if (!isLabelVisible) return null;
            return (
              <text
                key={i}
                x={p.x}
                y={height - 6}
                fill="rgb(82, 82, 91)"
                fontSize="10"
                fontWeight="850"
                textAnchor="middle"
                className="select-none"
              >
                {p.date}
              </text>
            );
          })}

          {/* 호버 세로선 */}
          {hoveredIndex !== null && (
            <line
              x1={points[hoveredIndex].x}
              y1={padding}
              x2={points[hoveredIndex].x}
              y2={height - padding}
              stroke="rgba(99, 102, 241, 0.3)"
              strokeWidth="1.5"
              strokeDasharray="2 2"
              className="pointer-events-none"
            />
          )}

          {/* 호버 정밀 원 */}
          {hoveredIndex !== null && (
            <g className="pointer-events-none">
              <circle
                cx={points[hoveredIndex].x}
                cy={points[hoveredIndex].y}
                r="6.5"
                fill="rgb(99, 102, 241)"
                fillOpacity="0.25"
              />
              <circle
                cx={points[hoveredIndex].x}
                cy={points[hoveredIndex].y}
                r="4"
                fill="#ffffff"
                stroke="rgb(99, 102, 241)"
                strokeWidth="2"
              />
            </g>
          )}
        </svg>

        {/* HTML 툴팁 */}
        {hoveredIndex !== null && (
          <div
            className="absolute z-50 pointer-events-none bg-zinc-900 border border-zinc-800 rounded-lg py-2 px-3 shadow-xl backdrop-blur-md transition-all duration-75 ease-out"
            style={{
              left: `${tooltipPos.x}px`,
              top: `${tooltipPos.y}px`,
              transform: "translateX(-50%)",
            }}
          >
            <div className="flex flex-col gap-0.5 items-center">
              <span className="text-[9px] text-zinc-500 font-bold uppercase tracking-wider">
                {chartData[hoveredIndex].date}
              </span>
              <span className="text-xs font-black text-white">
                {formatCurrency(chartData[hoveredIndex].usd)}
              </span>
            </div>
          </div>
        )}
      </div>

      {/* 하단 미니 상태 바 */}
      <div className="flex justify-between items-center mt-4 pt-3 border-t border-zinc-900/50">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gradient-to-r from-blue-500 to-indigo-500" />
          <span className="text-[10px] text-zinc-500 font-black">{t("asset_chart.live_asset")}</span>
        </div>
        <div className="flex gap-4">
          <span className="text-[9px] text-zinc-600 font-bold">{t("asset_chart.fx_note", { rate: fxRate.toLocaleString() })}</span>
        </div>
      </div>
    </div>
  );
}
