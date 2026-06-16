'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { adminAPI, isCancel } from '@/lib/api';
import { 
  Trophy, 
  Activity, 
  TrendingDown, 
  TrendingUp, 
  RefreshCw, 
  Loader2, 
  AlertTriangle,
  ChevronRight,
  Calendar
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  Legend 
} from 'recharts';
import { toast } from "sonner";
import { reportHandledError } from '@/lib/utils';

interface TickerStat {
  buys: number;
  sells: number;
  pnl: number;
}

interface EquityPoint {
  timestamp: string;
  total: number;
}

interface StrategyResult {
  strategy_type?: string;
  name: string;
  final_value: number;
  total_pnl: number;
  total_return_rate: number;
  mdd: number;
  total_trades: number;
  win_rate: number;
  sharpe_ratio?: number;
  sortino_ratio?: number;
  calmar_ratio?: number;
  selection_score?: number;
  selection_eligible?: boolean;
  confidence_grade?: string;
  data_basis?: string;
  data_quality_reason?: string;
  selection_exclusion_reasons?: string[];
  ticker_stats: Record<string, TickerStat>;
  equity_curve: EquityPoint[];
}



export function BacktestTournament() {
  const [data, setData] = useState<StrategyResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [isPolling, setIsPolling] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [selectedStrategy, setSelectedStrategy] = useState<StrategyResult | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);
  
  // 날짜 피커 제어 상태 (작년 2025년 디폴트)
  const [startDate, setStartDate] = useState("2025-01-01");
  const [endDate, setEndDate] = useState("2025-12-31");

  const fetchResults = useCallback(async (start: string, end: string) => {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setLoading(true);
    setIsPolling(false);
    setElapsedSeconds(0);

    const startTime = Date.now();
    const timerId = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    try {
      while (!controller.signal.aborted) {
        const res = await adminAPI.getBacktestTournament({
          params: { start_date: start, end_date: end },
          signal: controller.signal,
        });

        if (res.status === 202 || res.data?.status === 'processing') {
          setIsPolling(true);
          // Wait 10 seconds before polling again
          await new Promise(resolve => setTimeout(resolve, 10000));
        } else {
          const results = res.data?.data || res.data || [];
          setData(results);
          setSelectedStrategy(results[0] ?? null);
          break;
        }
      }
    } catch (error) {
      if (isCancel(error)) return;
      const msg = reportHandledError('Failed to fetch tournament results', error);
      toast.error(`대항전 결과 데이터 로드 실패: ${msg}`);
    } finally {
      clearInterval(timerId);
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
        setLoading(false);
        setIsPolling(false);
      }
    }
  }, []);

  useEffect(() => {
    // eslint-disable-next-line
    void fetchResults("2025-01-01", "2025-12-31");
    return () => {
      requestControllerRef.current?.abort();
    };
  }, [fetchResults]);

  const handleRunSimulation = () => {
    if (!startDate || !endDate) {
      toast.error("시작일과 종료일을 입력해주세요.");
      return;
    }
    // 날짜 논리성 선결 가드
    if (new Date(startDate) > new Date(endDate)) {
      toast.error("시작일은 종료일보다 이전이어야 합니다.");
      return;
    }
    toast.info(`${startDate} ~ ${endDate} 기간에 대한 HIL 시뮬레이션 배틀을 실행합니다.`);
    setLoading(true);
    void fetchResults(startDate, endDate);
  };

  const getRankBadge = (rank: number) => {
    switch (rank) {
      case 1:
        return (
          <span className="w-6 h-6 rounded-full bg-gradient-to-br from-amber-300 via-amber-500 to-yellow-600 text-slate-950 font-bold flex items-center justify-center text-xs shadow-md shadow-amber-500/20">
            1
          </span>
        );
      case 2:
        return (
          <span className="w-6 h-6 rounded-full bg-gradient-to-br from-slate-200 via-zinc-400 to-zinc-600 text-slate-950 font-bold flex items-center justify-center text-xs shadow-md shadow-slate-500/10">
            2
          </span>
        );
      case 3:
        return (
          <span className="w-6 h-6 rounded-full bg-gradient-to-br from-amber-600 via-amber-700 to-amber-900 text-slate-100 font-bold flex items-center justify-center text-xs">
            3
          </span>
        );
      default:
        return (
          <span className="w-6 h-6 rounded-full bg-zinc-800 text-zinc-400 font-bold flex items-center justify-center text-xs border border-zinc-700/50">
            {rank}
          </span>
        );
    }
  };

  const getReturnBadge = (rate: number) => {
    const isPositive = rate > 0;
    return (
      <span className={`px-2.5 py-1 rounded-lg text-xs font-bold font-mono tracking-tight flex items-center gap-1 w-fit
        ${isPositive 
          ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' 
          : 'bg-rose-500/10 text-rose-400 border border-rose-500/20'}`}>
        {isPositive ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
        {rate > 0 ? '+' : ''}{rate.toFixed(2)}%
      </span>
    );
  };

  // Recharts를 위한 5개 전략 자산 평가곡선 병합 데이터 산출
  const getChartData = () => {
    if (!data || data.length === 0) return [];
    
    // 첫 번째 성적 기준 타임라인 소싱
    const baseCurve = data[0].equity_curve || [];
    
    return baseCurve.map((entry, index) => {
      const dateOnly = entry.timestamp.split(' ')[0]; // YYYY-MM-DD
      const chartItem: Record<string, string | number> = { timestamp: dateOnly };
      
      data.forEach((strat) => {
        const curvePoint = strat.equity_curve?.[index] || strat.equity_curve?.[strat.equity_curve.length - 1];
        if (curvePoint) {
          chartItem[strat.name] = Math.round(curvePoint.total);
        }
      });
      return chartItem;
    });
  };

  // 순위에 대응하는 차트 선 색상 파레트
  const getLineColor = (index: number) => {
    const colors = [
      '#f59e0b', // 1위: Gold (Yellow-500)
      '#3b82f6', // 2위: Blue-500
      '#10b981', // 3위: Emerald-500
      '#ec4899', // 4위: Pink-500
      '#8b5cf6', // 5위: Purple-500
      '#06b6d4', // 6위: Cyan-500
      '#f43f5e', // 7위: Rose-500
    ];
    return colors[index] || '#64748b';
  };

  const chartData = getChartData();

  return (
    <div className="space-y-6">
      
      {/* 아레나 헤더 및 날짜 캘린더 피커 컨트롤 바 */}
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-4">
        <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between border-b border-zinc-800 pb-4 gap-4">
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-slate-100 flex items-center gap-2.5">
              <Trophy className="text-amber-400 animate-pulse" size={22} />
              배틀 아레나 (종합 백테스트 대항전)
            </h2>
            <p className="text-xs text-zinc-400">
              스윙 스캐너가 실시간 발굴한 포트폴리오를 대입하여 각 전략이 과거 시간 축에서 일궈낸 자산 성장 곡선을 동적으로 시뮬레이션합니다.
            </p>
          </div>
          
          {/* 동적 날짜 피커 UI 패널 */}
          <div className="flex flex-wrap items-center gap-3 bg-zinc-950/80 p-2 rounded-xl border border-zinc-850 shadow-inner">
            <div className="flex items-center gap-2 px-2.5">
              <Calendar size={14} className="text-zinc-500" />
              <span className="text-[11px] font-bold text-zinc-400 uppercase tracking-wider">시뮬레이션 기간</span>
            </div>
            
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded-lg px-2 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-zinc-700"
            />
            <span className="text-zinc-600 text-xs font-semibold">~</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="bg-zinc-900 border border-zinc-800 rounded-lg px-2 py-1.5 text-xs text-slate-200 font-mono focus:outline-none focus:border-zinc-700"
            />

            <button
              onClick={handleRunSimulation}
              disabled={loading}
              className="flex items-center justify-center gap-2 px-4 py-1.5 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-bold rounded-lg transition-all active:scale-95 cursor-pointer shadow-md shadow-blue-500/10"
            >
              {loading ? (
                <Loader2 size={13} className="animate-spin text-white" />
              ) : (
                <RefreshCw size={13} className="text-white" />
              )}
              대항전 매칭 실행
            </button>
          </div>
        </div>

        {loading ? (
          <div className="py-36 flex flex-col items-center justify-center gap-4">
            <Loader2 size={44} className="animate-spin text-blue-500" />
            <div className="text-center space-y-2">
              {isPolling ? (
                <>
                  <div className="flex items-center justify-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                    <span className="text-xs text-emerald-400 font-bold tracking-wider">서버에서 백그라운드 시뮬레이션을 진행 중입니다...</span>
                  </div>
                  <span className="text-[11px] text-zinc-400 block font-mono bg-zinc-900/50 py-1 px-3 rounded-full border border-zinc-800 inline-block">
                    경과 시간: {Math.floor(elapsedSeconds / 60).toString().padStart(2, '0')}:{(elapsedSeconds % 60).toString().padStart(2, '0')} (약 3~4분 소요)
                  </span>
                  <span className="text-[10px] text-zinc-500 block">이 화면을 벗어나도 백테스트는 계속 진행됩니다.</span>
                </>
              ) : (
                <>
                  <span className="text-xs text-slate-300 font-bold tracking-wider animate-pulse block">HIL 시뮬레이터 가상 환경 기동 중...</span>
                  <span className="text-[10px] text-zinc-500 block">yfinance 로컬 캐시로부터 15개 기술 지표 오실레이터 및 수급 벡터 로딩 중</span>
                </>
              )}
            </div>
          </div>
        ) : data.length === 0 ? (
          <div className="py-24 text-center space-y-3">
            <AlertTriangle className="mx-auto text-amber-500/80" size={48} />
            <h3 className="text-slate-300 font-bold">대항전 시뮬레이션 결과 없음</h3>
            <p className="text-xs text-zinc-500 max-w-sm mx-auto">
              입력하신 기간({startDate} ~ {endDate})에 매칭된 거래 이력이 없거나 데이터를 수집하지 못했습니다. 날짜 범위를 다시 확인해 주세요.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            
            {/* 상단 비교 곡선 차트 패널 */}
            <div className="bg-slate-950/80 border border-zinc-900 rounded-2xl p-5 shadow-2xl space-y-4">
              <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-500 block">
                Relative Asset Growth Curves (누적 자산 성장 곡선 비교)
              </span>
              
              <div className="h-[320px] min-h-[320px] w-full min-w-0 overflow-hidden text-slate-400">
                <ResponsiveContainer width="100%" height={320} minWidth={0} minHeight={240}>
                  <LineChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b/30" vertical={false} />
                    <XAxis 
                      dataKey="timestamp" 
                      stroke="#475569" 
                      fontSize={10} 
                      tickLine={false} 
                      axisLine={false}
                    />
                    <YAxis 
                      stroke="#475569" 
                      fontSize={10} 
                      tickLine={false} 
                      axisLine={false}
                      tickFormatter={(v) => `$${v.toLocaleString()}`}
                    />
                    <Tooltip 
                      contentStyle={{ backgroundColor: '#090d16', border: '1px solid #334155', borderRadius: '12px', fontSize: '11px', color: '#cbd5e1' }}
                      formatter={(value: number | string | readonly (number | string)[] | undefined) => {
                        const numericValue = typeof value === 'number' ? value : Number(value);
                        return [`$${(numericValue || 0).toLocaleString()}`, ''];
                      }}
                    />
                    <Legend 
                      verticalAlign="top" 
                      height={36} 
                      iconType="circle"
                      iconSize={8}
                      wrapperStyle={{ fontSize: '11px', fontWeight: 'bold' }}
                    />
                    {data.map((strat, idx) => (
                      <Line
                        key={strat.name}
                        type="monotone"
                        dataKey={strat.name}
                        stroke={getLineColor(idx)}
                        strokeWidth={idx === 0 ? 2.5 : 1.5}
                        dot={false}
                        activeDot={{ r: 4 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              
              {/* 좌측 성적 테이블 리더보드 */}
              <div className="lg:col-span-7 space-y-4">
                <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-500 block">
                  Tournament Rankings
                </span>

                <div className="border border-zinc-800/80 rounded-2xl overflow-hidden bg-slate-950/60 shadow-2xl">
                  <div className="overflow-x-auto">
                    <table className="w-full text-left border-collapse">
                      <thead>
                        <tr className="bg-zinc-900/60 border-b border-zinc-800/60 text-zinc-400 font-semibold text-[11px] uppercase tracking-wider">
                          <th className="py-3 px-4 text-center w-12">순위</th>
                          <th className="py-3 px-4">전략 명칭</th>
                          <th className="py-3 px-4 text-right">선발 점수</th>
                          <th className="py-3 px-4 text-right">최종 자산</th>
                          <th className="py-3 px-4">누적수익률</th>
                          <th className="py-3 px-4 text-right">MDD</th>
                          <th className="py-3 px-4 text-center">총 거래</th>
                          <th className="py-3 px-4 text-center w-8"></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-900/50">
                        {data.map((r, index) => {
                          const rank = index + 1;
                          const isSelected = selectedStrategy?.name === r.name;
                          return (
                            <tr
                              key={r.name}
                              onClick={() => setSelectedStrategy(r)}
                              className={`text-xs transition-all duration-300 cursor-pointer hover:bg-zinc-800/20
                                ${isSelected ? 'bg-zinc-800/35 border-l-2 border-l-blue-500' : 'bg-transparent'}`}
                            >
                              <td className="py-3.5 px-4 text-center font-bold">
                                <div className="flex justify-center">{getRankBadge(rank)}</div>
                              </td>
                              <td className="py-3.5 px-4 font-semibold text-slate-200">
                                <div className="flex items-center gap-2">
                                  <span>{r.name}</span>
                                  {r.confidence_grade && (
                                    <span className={`rounded px-1.5 py-0.5 text-[9px] font-black
                                      ${r.selection_eligible
                                        ? 'bg-blue-500/10 text-blue-300 border border-blue-500/20'
                                        : 'bg-amber-500/10 text-amber-300 border border-amber-500/20'}`}>
                                      {r.confidence_grade}
                                    </span>
                                  )}
                                </div>
                              </td>
                              <td className="py-3.5 px-4 text-right font-mono font-bold text-blue-300">
                                {r.selection_score !== undefined ? r.selection_score.toFixed(2) : '-'}
                              </td>
                              <td className="py-3.5 px-4 text-right font-mono font-bold text-slate-300">
                                ${r.final_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                              </td>
                              <td className="py-3.5 px-4">
                                {getReturnBadge(r.total_return_rate)}
                              </td>
                              <td className="py-3.5 px-4 text-right font-mono font-bold text-rose-400/90">
                                {r.mdd.toFixed(2)}%
                              </td>
                              <td className="py-3.5 px-4 text-center font-mono text-zinc-400 font-medium">
                                {r.total_trades}회
                              </td>
                              <td className="py-3.5 px-4 text-center text-zinc-600">
                                <ChevronRight size={14} className={isSelected ? 'text-blue-400 animate-pulse' : 'text-zinc-600'} />
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>

                <div className="bg-gradient-to-br from-blue-950/10 via-zinc-900/40 to-slate-900/60 rounded-2xl border border-blue-900/10 p-5 space-y-2 shadow-inner">
                  <div className="flex items-center gap-2 text-blue-400 font-bold text-xs uppercase">
                    <Activity size={14} />
                    동적 포트폴리오 감시 규칙
                  </div>
                  <p className="text-[11px] text-zinc-400 leading-relaxed">
                    선택하신 기간 동안 yfinance OHLCV 시계열 데이터가 동적 가상화되어 흘러갔습니다. 
                    지갑 분할 오케스트레이션과 QQQ 레짐 모드가 과거 날짜축 상에서 완벽히 동기화되어 매입/매도를 정밀 집행했습니다.
                    RVOL 2.0배 이상 매집 흔적이 수렴된 종목들만 매칭된 결과를 제공합니다.
                  </p>
                </div>
              </div>

              {/* 우측 종목별 상세 현황판 */}
              <div className="lg:col-span-5 space-y-4">
                {selectedStrategy && (
                  <>
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-zinc-500 block">
                        Slot Detail: {selectedStrategy.name.replace(/[^a-zA-Z0-9가-힣\s]/g, "").trim()}
                      </span>
                      <span className="text-[10px] text-zinc-400 font-bold font-mono bg-zinc-800 px-2 py-0.5 rounded">
                        승률 {selectedStrategy.win_rate.toFixed(2)}%
                      </span>
                    </div>

                    <div className="bg-[#0b0f19] border border-zinc-800/80 rounded-2xl p-5 shadow-2xl space-y-4">
                      
                      <div className="grid grid-cols-2 gap-3">
                        <div className="bg-zinc-900/40 rounded-xl p-3.5 border border-zinc-800/40">
                          <span className="text-[9px] uppercase font-bold tracking-wider text-zinc-500 block mb-1">
                            누적 순손익
                          </span>
                          <span className={`text-base font-mono font-extrabold block
                            ${selectedStrategy.total_pnl > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                            ${selectedStrategy.total_pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </span>
                        </div>
                        <div className="bg-zinc-900/40 rounded-xl p-3.5 border border-zinc-800/40">
                          <span className="text-[9px] uppercase font-bold tracking-wider text-zinc-500 block mb-1">
                            수익률 및 MDD
                          </span>
                          <div className="flex items-baseline gap-1.5">
                            <span className={`text-base font-mono font-extrabold block
                              ${selectedStrategy.total_return_rate > 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {selectedStrategy.total_return_rate.toFixed(2)}%
                            </span>
                            <span className="text-[10px] text-rose-500 font-bold font-mono">
                              (MDD {selectedStrategy.mdd.toFixed(1)}%)
                            </span>
                          </div>
                        </div>
                      </div>

                      {selectedStrategy.selection_score !== undefined && (
                        <div className="grid grid-cols-3 gap-3">
                          <div className="bg-zinc-900/40 rounded-xl p-3 border border-zinc-800/40">
                            <span className="text-[9px] uppercase font-bold tracking-wider text-zinc-500 block mb-1">
                              선발 점수
                            </span>
                            <span className="text-sm font-mono font-extrabold text-blue-300">
                              {selectedStrategy.selection_score.toFixed(2)}
                            </span>
                          </div>
                          <div className="bg-zinc-900/40 rounded-xl p-3 border border-zinc-800/40">
                            <span className="text-[9px] uppercase font-bold tracking-wider text-zinc-500 block mb-1">
                              Sharpe
                            </span>
                            <span className="text-sm font-mono font-extrabold text-slate-200">
                              {(selectedStrategy.sharpe_ratio ?? 0).toFixed(2)}
                            </span>
                          </div>
                          <div className="bg-zinc-900/40 rounded-xl p-3 border border-zinc-800/40">
                            <span className="text-[9px] uppercase font-bold tracking-wider text-zinc-500 block mb-1">
                              데이터 근거
                            </span>
                            <span className="text-[10px] font-bold text-slate-300">
                              {selectedStrategy.data_basis ?? '-'}
                            </span>
                          </div>
                        </div>
                      )}

                      {selectedStrategy.selection_eligible === false && (
                        <div className="flex gap-2 rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-[11px] leading-relaxed text-amber-200">
                          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                          <span>
                            기본 10개 선발에서 제외됩니다. {selectedStrategy.selection_exclusion_reasons?.join(' ')}
                          </span>
                        </div>
                      )}

                      <div className="space-y-2 max-h-[280px] overflow-y-auto pr-1 scrollbar-thin scrollbar-thumb-zinc-800">
                        <div className="flex text-[10px] uppercase font-bold tracking-wider text-zinc-500 px-3 border-b border-zinc-800/50 pb-2">
                          <div className="w-16">종목</div>
                          <div className="w-20 text-center">거래 (매수/매도)</div>
                          <div className="flex-1 text-right">총 실현손익</div>
                        </div>
                        
                        {Object.keys(selectedStrategy.ticker_stats || {}).map((t) => {
                          const stat = selectedStrategy.ticker_stats[t] || { buys: 0, sells: 0, pnl: 0 };
                          const total = stat.buys + stat.sells;
                          const isProfit = stat.pnl > 0;
                          const isZero = total === 0;

                          return (
                            <div
                              key={t}
                              className={`flex items-center text-xs px-3 py-2.5 rounded-xl border transition-colors
                                ${isZero 
                                  ? 'bg-transparent border-transparent text-zinc-650' 
                                  : 'bg-zinc-900/20 border-zinc-800/40 hover:bg-zinc-800/30'}`}
                            >
                              <div className="w-16 font-extrabold text-slate-300">
                                {t}
                              </div>
                              
                              <div className="w-20 text-center font-mono font-semibold text-zinc-400 text-[11px]">
                                {isZero ? (
                                  <span className="text-zinc-700 italic">스킵 (0회)</span>
                                ) : (
                                  `${total}회 (${stat.buys}/${stat.sells})`
                                )}
                              </div>

                              <div className="flex-1 flex items-center justify-end gap-3 font-mono font-bold">
                                {isZero ? (
                                  <span className="text-zinc-750 font-normal">$0.00</span>
                                ) : (
                                  <>
                                    <span className={isProfit ? 'text-emerald-400' : 'text-rose-400'}>
                                      ${stat.pnl.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                    </span>
                                    <div className="w-1.5 h-6 rounded bg-zinc-900 overflow-hidden shrink-0">
                                      <div 
                                        className={`w-full rounded ${isProfit ? 'bg-emerald-500' : 'bg-rose-500'}`}
                                        style={{ height: `${Math.min(100, Math.max(15, (Math.abs(stat.pnl) / 5000) * 100))}%` }}
                                      ></div>
                                    </div>
                                  </>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </>
                )}
              </div>

            </div>
          </div>
        )}
      </div>

    </div>
  );
}
