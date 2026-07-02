'use client';

import React, { useState } from 'react';
import { AlertTriangle, Loader2, SlidersHorizontal } from 'lucide-react';
import useSWR from 'swr';
import { adminAPI, fetcher } from '@/lib/api';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/utils';

interface SystemSettingItem {
  key: string;
  value: boolean | number | string | Record<string, unknown> | null;
  default: boolean | number | string | Record<string, unknown> | null;
  value_type: string;
  category: string;
  description: string;
  is_runtime: boolean;
  is_public: boolean;
  updated_at: string | null;
  updated_by: number | null;
}

interface SystemSettingsResponse {
  settings: SystemSettingItem[];
}

const GEMINI_NEWS_SETTING_KEY = 'enable_gemini_news_analysis';

function formatBool(value: SystemSettingItem['value']) {
  return value ? 'ON' : 'OFF';
}

export function SystemSettings() {
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const { data, isLoading, mutate } = useSWR<SystemSettingsResponse>(
    '/admin/system-settings',
    fetcher,
    { revalidateOnFocus: false },
  );

  const settings = data?.settings || [];
  const geminiNewsSetting = settings.find((item) => item.key === GEMINI_NEWS_SETTING_KEY);

  const handleBooleanChange = async (key: string, value: boolean) => {
    setSavingKey(key);
    try {
      await adminAPI.updateSystemSetting(key, { value });
      await mutate();
      toast.success('시스템 설정이 저장되었습니다.');
    } catch (error) {
      toast.error(`시스템 설정 저장 실패: ${getErrorMessage(error)}`);
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-[#0f1524]/60 backdrop-blur-md rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-5">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <SlidersHorizontal size={18} className="text-emerald-400" />
              시스템 전역 설정
            </h2>
            <p className="text-xs text-zinc-400 mt-1">
              사용자별 투자 설정이 아닌 서비스 전체 런타임 정책만 관리합니다.
            </p>
          </div>
          <span className="text-[10px] text-emerald-300 font-semibold bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded">
            ADMIN ONLY
          </span>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-emerald-400" />
          </div>
        ) : geminiNewsSetting ? (
          <div className="bg-slate-950/50 border border-zinc-800/60 rounded-2xl p-5">
            <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
              <div className="min-w-0 space-y-3">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-sm font-bold text-slate-100">Gemini 뉴스 분석</h3>
                  <span className={`text-[10px] font-black px-2 py-0.5 rounded-full ${
                    geminiNewsSetting.value
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : 'bg-zinc-800 text-zinc-500 border border-zinc-700'
                  }`}>
                    {formatBool(geminiNewsSetting.value)}
                  </span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-zinc-900 text-zinc-500 border border-zinc-800">
                    {geminiNewsSetting.category}
                  </span>
                </div>

                <p className="text-xs text-zinc-400 leading-relaxed">
                  {geminiNewsSetting.description}
                </p>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
                  <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/30 p-3">
                    <span className="block text-zinc-500 mb-1">기본값</span>
                    <strong className="text-slate-200">{formatBool(geminiNewsSetting.default)}</strong>
                  </div>
                  <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/30 p-3">
                    <span className="block text-zinc-500 mb-1">런타임 반영</span>
                    <strong className="text-slate-200">{geminiNewsSetting.is_runtime ? 'YES' : 'NO'}</strong>
                  </div>
                  <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/30 p-3">
                    <span className="block text-zinc-500 mb-1">마지막 변경</span>
                    <strong className="text-slate-200">
                      {geminiNewsSetting.updated_at
                        ? new Date(geminiNewsSetting.updated_at).toLocaleString()
                        : '-'}
                    </strong>
                  </div>
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 shrink-0">
                {savingKey === geminiNewsSetting.key && (
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                )}
                <label className="relative inline-flex items-center cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={Boolean(geminiNewsSetting.value)}
                    disabled={savingKey === geminiNewsSetting.key}
                    onChange={(event) => handleBooleanChange(geminiNewsSetting.key, event.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-disabled:opacity-50 peer-checked:after:translate-x-5 after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:bg-zinc-500 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500 peer-checked:after:bg-white" />
                </label>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-2xl border border-red-500/20 bg-red-500/10 p-5">
            <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
            <span className="text-sm font-bold text-red-300">
              등록된 시스템 설정을 불러오지 못했습니다.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
