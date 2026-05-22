"use client";

import { useMemo, useState, useRef } from "react";
import { TradeLog } from "./TradeLogs";

interface AssetTrendChartProps {
  displayCurrency: "KRW" | "USD";
  logs: TradeLog[];
}

export function AssetTrendChart({ displayCurrency, logs }: AssetTrendChartProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  // FX 환율 상수 (모의 및 환산용 - 평균 1,350원 적용)
  const FX_RATE = 1350;

  // 1. 차트에 표시할 데이터 세트 가공 (실제 거래 이력을 추세로 반영하되, 없거나 부족할 시 고급 우상향 PoC 데이터 적용)
  const chartData = useMemo(() => {
    // 기본 모의 우상향 데이터 (자산 성장 흐름 시각화 PoC)
    const baseMockData = [
      { date: "05-12", usd: 10000 },
      { date: "05-13", usd: 10250 },
      { date: "05-14", usd: 10120 },
      { date: "05-15", usd: 10480 },
      { date: "05-16", usd: 10600 },
      { date: "05-17", usd: 10510 },
      { date: "05-18", usd: 10890 },
      { date: "05-19", usd: 11150 },
      { date: "05-20", usd: 10980 },
      { date: "05-21", usd: 11420 },
      { date: "05-22", usd: 11800 },
      { date: "05-23", usd: 12250 },
    ];

    // 만약 실제 로그가 있고 데이터가 유의미하다면 시뮬레이션 자산 변화를 만들어 연동
    if (logs && logs.length > 0) {
      let currentAssetUsd = 10000; // 가상 시작점
      const realPoints = [...logs]
        .reverse() // 과거 순으로 정렬
        .map((log, index) => {
          const dateObj = new Date(log.executed_at);
          const dateStr = `${String(dateObj.getMonth() + 1).padStart(2, "0")}-${String(
            dateObj.getDate()
          ).padStart(2, "0")}`;
          
          // 매수 시 수수료 발생 및 평가변동, 매도 시 실제 수익 확정 흐름을 모의 연산
          const change = log.trade_type === "BUY" ? -log.price * log.quantity * 0.001 : log.price * log.quantity * 0.05;
          currentAssetUsd += change;
          
          return {
            date: dateStr,
            usd: Math.round(currentAssetUsd),
          };
        });

      // 포인트가 너무 적으면 앞부분에 기본 데이터를 결합하여 미려한 선 유지
      if (realPoints.length < 5) {
        const dummyNeeded = 7 - realPoints.length;
        const dummyPrefix = baseMockData.slice(0, dummyNeeded).map((d, i) => ({
          date: d.date,
          usd: d.usd,
        }));
        return [...dummyPrefix, ...realPoints];
      }
      return realPoints.slice(-12); // 최근 12개 흐름만 표시
    }

    return baseMockData;
  }, [logs]);

  // 2. SVG 그래프 좌표 계산
  const width = 800;
  const height = 240;
  const padding = 24;

  const minVal = useMemo(() => Math.min(...chartData.map((d) => d.usd)) * 0.98, [chartData]);
  const maxVal = useMemo(() => Math.max(...chartData.map((d) => d.usd)) * 1.02, [chartData]);

  const points = useMemo(() => {
    return chartData.map((d, i) => {
      const x = padding + (i / (chartData.length - 1)) * (width - padding * 2);
      const y = height - padding - ((d.usd - minVal) / (maxVal - minVal)) * (height - padding * 2);
      return { x, y, ...d };
    });
  }, [chartData, minVal, maxVal]);

  // SVG Path 생성 (Area 채우기용 및 Line 선용)
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

  // 3. 포맷팅 헬퍼
  const formatCurrency = (usdVal: number) => {
    if (displayCurrency === "USD") {
      return `$${usdVal.toLocaleString()}`;
    } else {
      const krwVal = Math.round(usdVal * FX_RATE);
      return `${krwVal.toLocaleString()}원`;
    }
  };

  // 4. 인터랙티브 마우스 핸들러
  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement, MouseEvent>) => {
    if (!containerRef.current || points.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const svgMouseX = (mouseX / rect.width) * width;

    // 마우스와 가장 가까운 포인트 검색
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

    // 툴팁 위치 결정
    const hoveredPoint = points[closestIndex];
    const tooltipX = (hoveredPoint.x / width) * rect.width;
    const tooltipY = (hoveredPoint.y / height) * rect.height - 45;
    setTooltipPos({ x: tooltipX, y: tooltipY });
  };

  const handleMouseLeave = () => {
    setHoveredIndex(null);
  };

  // 5. 변화량 계산
  const firstVal = chartData[0]?.usd || 10000;
  const lastVal = chartData[chartData.length - 1]?.usd || 10000;
  const changePct = ((lastVal - firstVal) / firstVal) * 100;

  return (
    <div
      ref={containerRef}
      className="relative w-full bg-zinc-950/70 border border-zinc-900 rounded-2xl p-6 backdrop-blur-md overflow-hidden shadow-2xl transition-all duration-300 hover:border-zinc-800"
    >
      {/* 백그라운드 디자인 빛 번짐 효과 (Glow Effect) */}
      <div className="absolute -top-24 -left-24 w-80 h-80 bg-indigo-500/10 rounded-full blur-[100px] pointer-events-none" />
      <div className="absolute -bottom-24 -right-24 w-80 h-80 bg-blue-500/5 rounded-full blur-[100px] pointer-events-none" />

      {/* 헤더 정보 */}
      <div className="flex justify-between items-start mb-6">
        <div>
          <span className="text-xs text-zinc-500 font-bold tracking-wider uppercase">
            자산 성장 추이 (Asset Growth Trend)
          </span>
          <div className="flex items-baseline gap-3 mt-1">
            <h3 className="text-2xl font-black text-white tracking-tight">
              {hoveredIndex !== null
                ? formatCurrency(chartData[hoveredIndex].usd)
                : formatCurrency(lastVal)}
            </h3>
            <span
              className={`text-xs font-extrabold px-2 py-0.5 rounded-full ${
                changePct >= 0 ? "bg-emerald-950/50 text-emerald-400" : "bg-red-950/50 text-red-400"
              }`}
            >
              {changePct >= 0 ? "+" : ""}
              {changePct.toFixed(2)}%
            </span>
          </div>
          <p className="text-[10px] text-zinc-600 mt-1">
            {hoveredIndex !== null
              ? `선택 시점: ${chartData[hoveredIndex].date}`
              : `기준 기간: 최근 ${chartData.length}일 흐름 (PoC)`}
          </p>
        </div>
      </div>

      {/* 실질 SVG 차트 영역 */}
      <div className="relative w-full h-[240px]">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-full cursor-crosshair overflow-visible"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          <defs>
            {/* 네온 블루-퍼플 테마 그라데이션 필터 */}
            <linearGradient id="chart-gradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="rgb(99, 102, 241)" stopOpacity="0.3" />
              <stop offset="60%" stopColor="rgb(59, 130, 246)" stopOpacity="0.1" />
              <stop offset="100%" stopColor="rgb(30, 41, 59)" stopOpacity="0.0" />
            </linearGradient>
            <linearGradient id="line-gradient" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="rgb(59, 130, 246)" />
              <stop offset="50%" stopColor="rgb(99, 102, 241)" />
              <stop offset="100%" stopColor="rgb(168, 85, 247)" />
            </linearGradient>
          </defs>

          {/* 격자 수평 보조선 */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
            const y = padding + ratio * (height - padding * 2);
            return (
              <line
                key={i}
                x1={padding}
                y1={y}
                x2={width - padding}
                y2={y}
                stroke="rgba(63, 63, 70, 0.15)"
                strokeWidth="1"
                strokeDasharray="4 4"
              />
            );
          })}

          {/* 그라데이션 배경 면적 */}
          {areaPath && (
            <path
              d={areaPath}
              fill="url(#chart-gradient)"
              className="transition-all duration-500 ease-out"
            />
          )}

          {/* 메인 선 */}
          {linePath && (
            <path
              d={linePath}
              fill="none"
              stroke="url(#line-gradient)"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="transition-all duration-500 ease-out"
            />
          )}

          {/* X축 날짜 텍스트 라벨 */}
          {points.map((p, i) => {
            // 가독성을 위해 첫점, 끝점 및 중간 몇개만 노출
            const isLabelVisible = i === 0 || i === points.length - 1 || i === Math.floor(points.length / 2);
            if (!isLabelVisible) return null;
            return (
              <text
                key={i}
                x={p.x}
                y={height - 6}
                fill="rgb(113, 113, 122)"
                fontSize="10"
                fontWeight="700"
                textAnchor="middle"
                className="select-none"
              >
                {p.date}
              </text>
            );
          })}

          {/* 호버 가이드 세로선 */}
          {hoveredIndex !== null && (
            <line
              x1={points[hoveredIndex].x}
              y1={padding}
              x2={points[hoveredIndex].x}
              y2={height - padding}
              stroke="rgba(99, 102, 241, 0.4)"
              strokeWidth="1.5"
              strokeDasharray="2 2"
              className="pointer-events-none"
            />
          )}

          {/* 호버링 중인 정밀 포인트 Dot */}
          {hoveredIndex !== null && (
            <g className="pointer-events-none">
              {/* 바깥쪽 글로우 원 */}
              <circle
                cx={points[hoveredIndex].x}
                cy={points[hoveredIndex].y}
                r="7"
                fill="rgb(99, 102, 241)"
                fillOpacity="0.3"
              />
              {/* 안쪽 핵심 원 */}
              <circle
                cx={points[hoveredIndex].x}
                cy={points[hoveredIndex].y}
                r="4.5"
                fill="#ffffff"
                stroke="rgb(99, 102, 241)"
                strokeWidth="2.5"
              />
            </g>
          )}
        </svg>

        {/* 세련된 HTML 플로팅 툴팁 (Micro-Interaction) */}
        {hoveredIndex !== null && (
          <div
            className="absolute z-10 pointer-events-none bg-zinc-900/90 border border-zinc-800 rounded-lg py-2 px-3 shadow-xl backdrop-blur-md transition-all duration-75 ease-out"
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

      {/* 하단 미니 레전드 뷰 */}
      <div className="flex justify-between items-center mt-4 pt-3 border-t border-zinc-900/50">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-gradient-to-r from-blue-500 to-indigo-500" />
          <span className="text-[10px] text-zinc-500 font-semibold">순자산 흐름 (Net Worth)</span>
        </div>
        <div className="flex gap-4">
          <span className="text-[9px] text-zinc-600 font-medium">최저: {formatCurrency(Math.round(minVal / 0.98))}</span>
          <span className="text-[9px] text-zinc-600 font-medium">최고: {formatCurrency(Math.round(maxVal / 1.02))}</span>
        </div>
      </div>
    </div>
  );
}
