import { useState, useEffect, useCallback } from 'react';
import { systemAPI } from '../lib/api';

export interface HealthCore {
  redis: { status: string; latency_ms: number };
  database: { status: string; latency_ms: number; type: string };
  resources: { memory_usage_percent: number; disk_usage_percent: number; memory_warning: boolean; disk_warning: boolean };
}

export interface HealthBot {
  scheduler: { is_running: boolean; jobs_count: number };
  trading_loop: { is_processing: boolean };
}

export interface HealthBrokers {
  // status: "connected" | "disconnected" | "not_implemented"
  // latency_ms는 미구현(not_implemented) 상태에서 null이다.
  kis: { status: string; latency_ms: number | null; rate_limit_warning: boolean };
  toss: { status: string; latency_ms: number | null; rate_limit_warning: boolean };
}

export function useSystemHealth(intervalMs: number = 0) {
  const [core, setCore] = useState<HealthCore | null>(null);
  const [bot, setBot] = useState<HealthBot | null>(null);
  const [brokers, setBrokers] = useState<HealthBrokers | null>(null);
  const [loadingCore, setLoadingCore] = useState(true);
  const [loadingBot, setLoadingBot] = useState(true);
  const [loadingBrokers, setLoadingBrokers] = useState(true);

  const fetchHealth = useCallback(() => {
    setLoadingCore(true);
    setLoadingBot(true);
    setLoadingBrokers(true);

    systemAPI.getHealthCore()
      .then(res => setCore(res.data))
      .catch(() => setCore(null))
      .finally(() => setLoadingCore(false));

    systemAPI.getHealthBot()
      .then(res => setBot(res.data))
      .catch(() => setBot(null))
      .finally(() => setLoadingBot(false));

    systemAPI.getHealthBrokers()
      .then(res => setBrokers(res.data))
      .catch(() => setBrokers(null))
      .finally(() => setLoadingBrokers(false));
  }, []);

  useEffect(() => {
    // 최초 1회 즉시 호출
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchHealth();

    // 주기가 0이거나 꺼져있으면 인터벌 등록 안함
    if (intervalMs <= 0) return;

    let intervalId: NodeJS.Timeout;

    const startPolling = () => {
      intervalId = setInterval(() => {
        // 화면이 보일 때만 갱신 (탭 전환 시 정지)
        if (document.visibilityState === 'visible') {
          fetchHealth();
        }
      }, intervalMs);
    };

    const stopPolling = () => {
      if (intervalId) clearInterval(intervalId);
    };

    // 포커스가 돌아왔을 때 즉시 1회 갱신 후 폴링 재시작
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        fetchHealth();
      }
    };

    startPolling();
    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      stopPolling();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [fetchHealth, intervalMs]);

  return {
    core,
    bot,
    brokers,
    loadingCore,
    loadingBot,
    loadingBrokers,
    refetch: fetchHealth,
  };
}
