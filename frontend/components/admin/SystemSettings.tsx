'use client';

import React, { useState } from 'react';
import { AlertTriangle, Loader2, SlidersHorizontal } from 'lucide-react';
import useSWR from 'swr';
import { adminAPI, fetcher } from '@/lib/api';
import { toast } from 'sonner';
import { getErrorMessage } from '@/lib/utils';
import { useTranslations } from "next-intl";

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
const SCANNER_RELAY_SETTING_KEY = 'enable_scanner_relay';

// 화면에 노출할 설정과 그 한글 제목. 백엔드 스펙의 description은 영문이라 제목만 여기서 관리한다.
// 설정이 늘어나면 이 맵 대신 목록 순회 렌더링으로 일반화할 것(i18n 라벨 전략 확정 후).
const MANAGED_SETTING_KEYS = [GEMINI_NEWS_SETTING_KEY, SCANNER_RELAY_SETTING_KEY];
const SETTING_TITLES: Record<string, string> = {
  [GEMINI_NEWS_SETTING_KEY]: 'label_gemini',
  [SCANNER_RELAY_SETTING_KEY]: 'label_relay',
};

function formatBool(value: SystemSettingItem['value']) {
  return value ? 'ON' : 'OFF';
}

interface SettingCardProps {
  item: SystemSettingItem;
  saving: boolean;
  onChange: (key: string, value: boolean) => void;
}

function SettingCard({ item, saving, onChange }: SettingCardProps) {
  const t = useTranslations("admin_ui");
  return (
    <div className="bg-slate-950/50 border border-zinc-800/60 rounded-2xl p-5">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-5">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-bold text-slate-100">{SETTING_TITLES[item.key] ? t(`settings.${SETTING_TITLES[item.key]}`) : item.key}</h3>
            <span className={`text-[10px] font-black px-2 py-0.5 rounded-full ${
              item.value
                ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                : 'bg-zinc-800 text-zinc-500 border border-zinc-700'
            }`}>
              {formatBool(item.value)}
            </span>
            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-zinc-900 text-zinc-500 border border-zinc-800">
              {item.category}
            </span>
          </div>

          <p className="text-xs text-zinc-400 leading-relaxed">
            {item.description}
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-[11px]">
            <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/30 p-3">
              <span className="block text-zinc-500 mb-1">{t("settings.default_value")}</span>
              <strong className="text-slate-200">{formatBool(item.default)}</strong>
            </div>
            <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/30 p-3">
              <span className="block text-zinc-500 mb-1">{t("settings.runtime_applied")}</span>
              <strong className="text-slate-200">{item.is_runtime ? 'YES' : 'NO'}</strong>
            </div>
            <div className="rounded-xl border border-zinc-800/60 bg-zinc-900/30 p-3">
              <span className="block text-zinc-500 mb-1">{t("settings.last_changed")}</span>
              <strong className="text-slate-200">
                {item.updated_at ? new Date(item.updated_at).toLocaleString() : '-'}
              </strong>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 shrink-0">
          {saving && <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />}
          <label className="relative inline-flex items-center cursor-pointer select-none">
            <input
              type="checkbox"
              checked={Boolean(item.value)}
              disabled={saving}
              onChange={(event) => onChange(item.key, event.target.checked)}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-zinc-800 peer-focus:outline-none rounded-full peer peer-disabled:opacity-50 peer-checked:after:translate-x-5 after:content-[''] after:absolute after:top-[3px] after:left-[3px] after:bg-zinc-500 after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-500 peer-checked:after:bg-white" />
          </label>
        </div>
      </div>
    </div>
  );
}

export function SystemSettings() {
  const t = useTranslations("admin_ui");
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const { data, isLoading, mutate } = useSWR<SystemSettingsResponse>(
    '/admin/system-settings',
    fetcher,
    { revalidateOnFocus: false },
  );

  const settings = data?.settings || [];
  const managedSettings = MANAGED_SETTING_KEYS
    .map((key) => settings.find((item) => item.key === key))
    .filter((item): item is SystemSettingItem => Boolean(item));

  const handleBooleanChange = async (key: string, value: boolean) => {
    setSavingKey(key);
    try {
      await adminAPI.updateSystemSetting(key, { value });
      await mutate();
      toast.success(t("settings.save_success"));
    } catch (error) {
      toast.error(t("settings.save_failed", { error: getErrorMessage(error) }));
    } finally {
      setSavingKey(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-surface-card/80 backdrop-blur-xl rounded-2xl border border-zinc-800/80 p-6 shadow-xl space-y-5">
        <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
          <div>
            <h2 className="text-lg font-bold text-slate-100 flex items-center gap-2">
              <SlidersHorizontal size={18} className="text-emerald-400" />
              {t("settings.title")}
            </h2>
            <p className="text-xs text-zinc-400 mt-1">
              {t("settings.subtitle")}
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
        ) : managedSettings.length > 0 ? (
          <div className="space-y-4">
            {managedSettings.map((item) => (
              <SettingCard
                key={item.key}
                item={item}
                saving={savingKey === item.key}
                onChange={handleBooleanChange}
              />
            ))}
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-2xl border border-red-500/20 bg-red-500/10 p-5">
            <AlertTriangle className="w-5 h-5 text-red-400 shrink-0" />
            <span className="text-sm font-bold text-red-300">
              {t("settings.load_failed")}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
